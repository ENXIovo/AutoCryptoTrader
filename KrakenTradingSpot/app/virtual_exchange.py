import time
import uuid
import logging
from typing import Dict, Any, Optional, Tuple

import redis

from app.config import settings
from app.data_client import DataClient

logger = logging.getLogger(__name__)


class VirtualExchange:
    """
    V1 虚拟撮合：基于 last_price 的简化撮合与事件发布。
    - 支持 market / limit 入场
    - post_only 与“越价”规则校验
    - 立即可成交的限价 → 视为即时成交（按 last_price）
    - 不可成交的限价 → 保持 open（本版本不推进后续撮合）
    - 事件发布到 Redis Stream: {settings.ORDER_EVENT_STREAM_PREFIX}{txid}
    - 返回结构尽量对齐 Kraken 风格
    """

    def __init__(self) -> None:
        self._orders: Dict[str, Dict[str, Any]] = {}  # txid -> order dict
        self._user_orders: Dict[str, set[str]] = {}   # userref -> {txid}
        self._r = redis.Redis.from_url(settings.REDIS_URL, decode_responses=True)
        self._data = DataClient()

    # ---------- Helpers ----------
    def _new_txid(self) -> str:
        return f"VIRT-{uuid.uuid4().hex[:16]}"

    def _stream_key(self, txid: str) -> str:
        return f"{settings.ORDER_EVENT_STREAM_PREFIX}{txid}"

    def _publish_event(self, txid: str, status: str, extra: Optional[Dict[str, Any]] = None) -> None:
        fields = {"status": status, "ts": str(time.time())}
        if extra:
            for k, v in extra.items():
                if v is not None:
                    fields[k] = str(v)
        try:
            self._r.xadd(self._stream_key(txid), fields)
        except Exception as e:
            logger.info(f"[VIRT] publish_event failed txid={txid} err={e}")

    def _post_only_violation(self, side: str, price: Optional[float], last_price: Optional[float], post_only: bool) -> bool:
        if not post_only or price is None or last_price is None:
            return False
        if side == "buy" and price >= last_price:
            return True
        if side == "sell" and price <= last_price:
            return True
        return False

    def _would_fill_now(self, side: str, price: Optional[float], last_price: Optional[float]) -> bool:
        if price is None or last_price is None:
            return False
        if side == "buy" and price >= last_price:
            return True
        if side == "sell" and price <= last_price:
            return True
        return False

    def _parse_oflags(self, oflags: Any) -> Tuple[bool, str]:
        """return (post_only, raw_string)"""
        if oflags is None:
            return (False, "")
        if isinstance(oflags, list):
            post_only = "post" in oflags
            return (post_only, ",".join(oflags))
        s = str(oflags)
        post_only = "post" in s.split(",")
        return (post_only, s)

    # ---------- Public-like API (Kraken compatible-ish) ----------
    async def add_order(self, order_data: Dict[str, Any]) -> Dict[str, Any]:
        userref = order_data.get("userref") or int(time.time())
        pair = str(order_data.get("pair") or "")  # 直接透传
        side = str(order_data.get("type") or "").lower()
        ordertype = str(order_data.get("ordertype") or "").lower()
        volume = float(order_data.get("volume") or 0.0)
        price = order_data.get("price")
        price = float(price) if price is not None else None

        post_only, oflags_raw = self._parse_oflags(order_data.get("oflags"))

        # 仅允许 market / limit 入场
        if ordertype not in {"market", "limit"}:
            return {"error": ["EOrder:Unsupported entry ordertype"], "result": {}}

        last_price = self._data.get_last_price(pair)
        if post_only and ordertype != "limit":
            return {"error": ["EOrder:post_only requires limit"], "result": {}}
        if self._post_only_violation(side, price, last_price, post_only):
            return {"error": ["EOrder:Post only order"], "result": {}}

        txid = self._new_txid()
        now = time.time()

        # 市价或者可立即成交的限价：直接成交
        if ordertype == "market" or self._would_fill_now(side, price, last_price):
            avg_price = last_price if last_price is not None else price
            self._orders[txid] = {
                "pair": pair,
                "type": side,
                "ordertype": ordertype,
                "volume": volume,
                "filled": volume,
                "avg_price": avg_price,
                "status": "closed",
                "userref": userref,
                "oflags": oflags_raw,
                "created_at": now,
                "closed_at": now,
            }
            self._user_orders.setdefault(str(userref), set()).add(txid)
            # 发布事件：closed
            self._publish_event(txid, "closed", {"vol": str(volume)})
            return {"error": [], "result": {"txid": [txid]}}

        # 否则：创建 open 订单（不继续撮合）
        self._orders[txid] = {
            "pair": pair,
            "type": side,
            "ordertype": ordertype,
            "volume": volume,
            "filled": 0.0,
            "status": "open",
            "userref": userref,
            "oflags": oflags_raw,
            "price": price,
            "created_at": now,
        }
        self._user_orders.setdefault(str(userref), set()).add(txid)
        # 发布事件：open（可选）
        self._publish_event(txid, "open", {"vol": str(volume)})
        return {"error": [], "result": {"txid": [txid]}}

    async def amend_order(self, amend_data: Dict[str, Any]) -> Dict[str, Any]:
        txid = str(amend_data.get("txid") or "")
        if not txid or txid not in self._orders:
            return {"error": ["EOrder:Unknown txid"], "result": {}}
        order = self._orders[txid]
        if order.get("status") != "open":
            # 简化：非 open 订单允许修改数量用于 SL（我们也允许，直接记录并发事件）
            if amend_data.get("order_qty") is not None:
                try:
                    new_vol = float(amend_data.get("order_qty"))
                    order["volume"] = new_vol
                except Exception:
                    pass
                self._publish_event(txid, "amended", {"vol": str(order.get("volume"))})
                return {"error": [], "result": {"amend_id": f"VIRT-AMEND-{txid}"}}
            return {"error": [], "result": {"amend_id": f"VIRT-NOOP-{txid}"}}

        # open 订单：支持修改 limit 价格或数量
        if amend_data.get("limit_price") is not None:
            try:
                order["price"] = float(amend_data.get("limit_price"))
            except Exception:
                pass
        if amend_data.get("order_qty") is not None:
            try:
                order["volume"] = float(amend_data.get("order_qty"))
            except Exception:
                pass

        # 若修改后立即可成交，则直接成交
        last_price = self._data.get_last_price(order.get("pair", ""))
        if self._would_fill_now(order.get("type", ""), order.get("price"), last_price):
            order["filled"] = order.get("volume", 0.0)
            order["avg_price"] = last_price if last_price is not None else order.get("price")
            order["status"] = "closed"
            order["closed_at"] = time.time()
            self._publish_event(txid, "closed", {"vol": str(order.get("filled"))})
        else:
            self._publish_event(txid, "amended", {"vol": str(order.get("volume"))})
        return {"error": [], "result": {"amend_id": f"VIRT-AMEND-{txid}"}}

    async def cancel_order(self, cancel_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        支持按 txid 或 userref 撤单。
        """
        count = 0
        txid = cancel_data.get("txid")
        userref = cancel_data.get("userref")

        targets: set[str] = set()
        if txid and txid in self._orders:
            targets.add(txid)
        if userref is not None:
            targets |= set(self._user_orders.get(str(userref), set()))

        for t in list(targets):
            od = self._orders.get(t)
            if not od:
                continue
            if od.get("status") in {"closed", "canceled"}:
                continue
            od["status"] = "canceled"
            od["canceled_at"] = time.time()
            self._publish_event(t, "canceled")
            count += 1
        return {"error": [], "result": {"count": count}}

    async def get_ticker(self, ticker_data: Dict[str, Any]) -> Dict[str, Any]:
        pair = ticker_data.get("pair")
        if not pair:
            return {"error": ["Pair is required for get_ticker"], "result": {}}
        last = self._data.get_last_price(str(pair))
        if last is None:
            return {"error": ["No last price"], "result": {}}
        # 对齐 Kraken 结果结构（最小必要字段）
        return {
            "error": [],
            "pair_key": str(pair),
            "altname": str(pair),
            "result": {
                "c": [str(last), "0"]  # Kraken c[0] 为 last price 字符串
            }
        }


# 单例
virtual_exch = VirtualExchange()


