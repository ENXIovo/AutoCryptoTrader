import asyncio
import time
import json
import websockets
import redis
import logging
from typing import Any, Dict, Optional

from app.config import settings
from app.kraken_client import KrakenClient
from app.ledger import ledger_instance as ledger
from app.models import TradeLedgerEntry, TradeStatus, OrderSide, OrderType, AddOrderRequest, AmendOrderRequest
from app.services import add_order_service, amend_order_service
logger = logging.getLogger(__name__)


class KrakenWSListener:
    def __init__(self) -> None:
        self._client = KrakenClient()
        self._ws_url = settings.KRAKEN_WS_AUTH_URL
        self._reconnect_backoff = settings.WS_RECONNECT_BACKOFF_SEC
        self._running = False
        self._redis = redis.Redis.from_url(settings.REDIS_URL, decode_responses=True)
        self._order_event_stream_prefix = settings.ORDER_EVENT_STREAM_PREFIX
        self._audit_stream_key = settings.ORDER_AUDIT_STREAM_KEY
        self._token: Optional[str] = None
        self._token_acquired_at: float = 0.0

    async def _subscribe_open_orders(self, ws, token: str) -> None:
        await ws.send(
            json.dumps({
                "event": "subscribe",
                "pair": [],  # 私有频道不需要 pair
                "subscription": {"name": "openOrders", "token": token},
            })
        )

    async def _subscribe_own_trades(self, ws, token: str) -> None:
        await ws.send(
            json.dumps({
                "event": "subscribe",
                "pair": [],
                "subscription": {"name": "ownTrades", "token": token},
            })
        )

    async def _handle_private_message(self, msg: Any) -> None:
        # 私有频道消息为列表，包含 [channelID, data, channelName, ...]
        if not isinstance(msg, list) or len(msg) < 3:
            return
        channel_name = msg[2]
        data = msg[1]
        if channel_name == "openOrders":
            await self._process_open_orders(data)
        elif channel_name == "ownTrades":
            # 可用于补充成交信息，目前主要依赖 openOrders 状态
            pass

    async def _process_open_orders(self, data: Dict[str, Any]) -> None:
        # 文档结构：{"open": {txid: {status, descr, vol, ...}}, "closed": {...}}
        # 我们只处理与 ledger 匹配的 symbol（通过 altname/descr.pair）和台账中记录的 stop_loss_txid
        open_map = data.get("open") or {}
        closed_map = data.get("closed") or {}

        # 检测陌生 open 订单（无 userref 或不匹配我们的台账 txid）并告警
        await self._detect_and_alert_foreign_open_orders(open_map)

        # 检查已关闭订单：
        for txid, od in (closed_map or {}).items():
            await self._maybe_handle_external_close(txid, od)

        # 开放订单中若发现我们的 stop_loss 被外部改量/改价，做一致性修正
        for txid, od in (open_map or {}).items():
            await self._maybe_reconcile_open_order(txid, od)
            # 若是由条件平仓生成的 SL 且台账暂无记录，则尝试识别并补录（确保后续等待逻辑能看到它）
            await self._maybe_attach_new_stop_loss(txid, od)
        # 快照对账：若 ledger 中存在 ACTIVE/TP1_HIT 的单，但既不在 open 也不在 closed，广播一个未知心跳，促使等待方继续等待
        known_txids = set((open_map or {}).keys()) | set((closed_map or {}).keys())
        for t in ledger.get_all_trades():
            for tx in filter(None, [getattr(t, "stop_loss_txid", None), getattr(t, "entry_txid", None)]):
                if tx not in known_txids:
                    await self._broadcast_order_event(tx, {"status": "unknown"})

    async def _maybe_handle_external_close(self, txid: str, order: Dict[str, Any]) -> None:
        trades = ledger.get_all_trades()
        for t in trades:
            # 1) 原入场单被关闭/取消：内部直接关闭交易
            if getattr(t, "entry_txid", None) == txid:
                def _close_entry(tr: TradeLedgerEntry):
                    tr.status = TradeStatus.CLOSED
                    return tr
                ledger.update_trade_atomically(t.symbol, _close_entry)
                ledger.delete_trade_by_id(t.trade_id)
                import logging as _logging
                _logging.getLogger(__name__).info(f"[WS] Entry order closed/canceled externally for {t.symbol}. Trade closed.")
                await self._broadcast_order_event(txid, order)
                return
            # 2) 止损单被关闭/取消：内部立即重挂止损
            if getattr(t, "stop_loss_txid", None) == txid:
                await self._broadcast_order_event(txid, order)
                await self._recreate_stop_loss(t)
                return

    async def _maybe_reconcile_open_order(self, txid: str, order: Dict[str, Any]) -> None:
        trades = ledger.get_all_trades()
        for t in trades:
            if t.stop_loss_txid == txid:
                # 同步数量 vol → remaining_size（若不一致）
                try:
                    current_vol = float(order.get("vol") or 0)
                except Exception:
                    return
                changed = False
                if abs(current_vol - t.remaining_size) >= 1e-12:
                    def _sync_size(tr: TradeLedgerEntry):
                        tr.remaining_size = current_vol
                        return tr
                    ledger.update_trade_atomically(t.symbol, _sync_size)
                    import logging as _logging
                    _logging.getLogger(__name__).info(f"[WS] Reconciled SL vol for {t.symbol}: {t.remaining_size} -> {current_vol}")
                    changed = True

                # 同步触发价（若可获取）
                stop_price = order.get("stopprice") or order.get("price")
                if stop_price is not None:
                    try:
                        sp = float(stop_price)
                        if abs(sp - t.stop_loss_price) >= 1e-12:
                            def _sync_sl(tr: TradeLedgerEntry):
                                tr.stop_loss_price = sp
                                return tr
                            ledger.update_trade_atomically(t.symbol, _sync_sl)
                            import logging as _logging
                            _logging.getLogger(__name__).info(f"[WS] Reconciled SL price for {t.symbol}: {t.stop_loss_price} -> {sp}")
                            changed = True
                    except Exception:
                        pass

                # 广播 open 心跳/变更事件
                await self._broadcast_order_event(txid, {**(order or {}), "status": order.get("status") or "open"})
                return

    async def _maybe_attach_new_stop_loss(self, txid: str, order: Dict[str, Any]) -> None:
        """识别由条件平仓生成的新止损单：
        - openOrders 里存在该 txid
        - 台账中尚无任何 trade.stop_loss_txid == txid
        - 其方向应与已有持仓方向相反（或根据 descr/type 字段判断）
        命中后将其回写到匹配的 trade（按 symbol 匹配，取 ACTIVE/TP1_HIT 状态的第一笔）。
        """
        try:
            symbol = None
            descr = order.get("descr") or {}
            if descr.get("pair"):
                # descr.pair 可能是 WSName，例如 XBT/USD → 我们的台账用 altname，但 symbol 字段一致
                symbol = (descr.get("pair") or "").replace("/", "")

            if not symbol:
                return

            # 提取可用于匹配的元信息
            uref = order.get("userref")
            side_str = (descr.get("type") or order.get("type") or "").lower()
            try:
                vol_f = float(order.get("vol") or 0.0)
            except Exception:
                vol_f = None
            # SL 价格（若存在）
            try:
                stop_price = None
                if order.get("stopprice") is not None:
                    stop_price = float(order.get("stopprice"))
                elif order.get("price") is not None:
                    stop_price = float(order.get("price"))
                elif descr.get("price") is not None:
                    stop_price = float(descr.get("price"))
            except Exception:
                stop_price = None

            # 生成候选 trades：同 symbol，状态 ACTIVE/TP1_HIT，且当前尚未绑定 SL txid
            candidates: list[TradeLedgerEntry] = [
                t for t in ledger.get_all_trades()
                if t.symbol == symbol and (t.stop_loss_txid in (None, "")) and (t.status in (TradeStatus.ACTIVE, TradeStatus.TP1_HIT))
            ]
            if not candidates:
                return

            # 1) 首选 userref 匹配
            if uref is not None:
                try:
                    uref_str = str(uref)
                    by_uref = [t for t in candidates if str(getattr(t, "userref", None)) == uref_str]
                    if by_uref:
                        candidates = by_uref
                except Exception:
                    pass

            # 2) 方向校验（SL 单方向应与持仓方向相反）
            if side_str in ("buy", "sell"):
                from app.models import OrderSide as _OS
                opposite = _OS.sell if side_str == "buy" else _OS.buy
                by_side = [t for t in candidates if getattr(t, "side", None) == opposite]
                if by_side:
                    candidates = by_side

            # 3) 体量/价格近似（可选增强，尽量不误绑）
            def _is_close(a: float, b: float, rel: float = 1e-6) -> bool:
                try:
                    return abs(float(a) - float(b)) <= rel * max(1.0, abs(float(b)))
                except Exception:
                    return False

            scored: list[tuple[int, TradeLedgerEntry]] = []
            for t in candidates:
                score = 0
                if vol_f is not None and _is_close(vol_f, getattr(t, "remaining_size", None) or 0.0):
                    score += 1
                if stop_price is not None and _is_close(stop_price, getattr(t, "stop_loss_price", None) or 0.0):
                    score += 1
                scored.append((score, t))

            # 选择评分最高者
            t_selected = max(scored, key=lambda x: x[0])[1] if scored else candidates[0]

            def _upd(tr: TradeLedgerEntry):
                tr.stop_loss_txid = txid
                return tr
            ledger.update_trade_atomically(t_selected.symbol, _upd)

            # 新止损单生成后，若其价格与台账不一致，则立即改单到台账价
            try:
                if stop_price is not None and abs(float(t_selected.stop_loss_price) - float(stop_price)) > 1e-9:
                    await amend_order_service(AmendOrderRequest(txid=txid, trigger_price=str(float(t_selected.stop_loss_price))))
                    import logging as _logging
                    _logging.getLogger(__name__).info(
                        f"[WS] Amended newly created SL price for {t_selected.symbol}: {stop_price} -> {t_selected.stop_loss_price}"
                    )
            except Exception as e:
                import logging as _logging
                _logging.getLogger(__name__).info(f"[WS] Failed to amend new SL to ledger price for {t_selected.symbol}: {e}")
            return
        except Exception:
            return

    async def _broadcast_order_event(self, txid: str, order: Dict[str, Any]) -> None:
        try:
            status = (order or {}).get("status") or "open"
            payload = {
                "status": status,
                "vol": str((order or {}).get("vol") or ""),
                "ts": str(int(time.time() * 1000)),
            }
            # 附带价格字段（若存在）
            if (order or {}).get("stopprice") is not None:
                payload["stopprice"] = str(order.get("stopprice"))
            if (order or {}).get("limitprice") is not None:
                payload["limitprice"] = str(order.get("limitprice"))
            if (order or {}).get("price") is not None:
                payload["price"] = str(order.get("price"))
            key = f"{self._order_event_stream_prefix}{txid}"
            self._redis.xadd(key, payload)
            # 设置 TTL（过期清理）
            try:
                ttl = int(settings.ORDER_EVENT_TTL_SEC)
                if ttl > 0:
                    self._redis.expire(key, ttl)
            except Exception:
                pass
        except Exception:
            pass

    async def _audit(self, kind: str, detail: Dict[str, Any]) -> None:
        try:
            payload = {"kind": kind, "ts": str(int(time.time() * 1000)), **{k: str(v) for k, v in (detail or {}).items()}}
            self._redis.xadd(self._audit_stream_key, payload)
        except Exception:
            pass

    async def _detect_and_alert_foreign_open_orders(self, open_map: Dict[str, Any]) -> None:
        if not open_map:
            return
        # 我方已知 txid 集合与 userref 集合
        known_txids = set()
        known_userrefs = set()
        for t in ledger.get_all_trades():
            if getattr(t, "entry_txid", None):
                known_txids.add(t.entry_txid)
            if getattr(t, "stop_loss_txid", None):
                known_txids.add(t.stop_loss_txid)
            if getattr(t, "userref", None) is not None:
                known_userrefs.add(str(t.userref))

        for txid, od in open_map.items():
            if txid in known_txids:
                continue
            uref = str(od.get("userref")) if od.get("userref") is not None else None
            # 条件：不在我方 userref 集合 → 视为陌生订单
            if uref is None or uref not in known_userrefs:
                descr = od.get("descr") or {}
                await self._audit("foreign_open_order", {
                    "txid": txid,
                    "userref": uref or "",
                    "ordertype": descr.get("ordertype") or od.get("ordertype") or "",
                    "type": descr.get("type") or od.get("type") or "",
                    "pair": descr.get("pair") or "",
                    "vol": od.get("vol") or "",
                    "price": descr.get("price") or od.get("price") or "",
                })

    async def _recreate_stop_loss(self, trade: TradeLedgerEntry) -> None:
        try:
            # 使用当前台账参数重挂 SL
            sl_payload = AddOrderRequest(
                pair=trade.symbol,
                type=OrderSide.sell if trade.side == OrderSide.buy else OrderSide.buy,
                ordertype=OrderType.stop_loss,
                price=str(trade.stop_loss_price),
                volume=str(trade.remaining_size),
            )
            new_txid = await add_order_service(sl_payload)
            def _upd(tr: TradeLedgerEntry):
                tr.stop_loss_txid = new_txid
                tr.status = TradeStatus.ACTIVE
                return tr
            ledger.update_trade_atomically(trade.symbol, _upd)
            import logging as _logging
            _logging.getLogger(__name__).info(f"[WS] Recreated SL for {trade.symbol}. New TXID={new_txid}")
        except Exception as e:
            import logging as _logging
            _logging.getLogger(__name__).info(f"[WS] Failed to recreate stop-loss for {trade.symbol}: {e}")

    async def run_forever(self) -> None:
        if not settings.WS_ENABLED:
            import logging as _logging
            _logging.getLogger(__name__).info("WS listener disabled via config.")
            return
        self._running = True
        while self._running:
            try:
                # 刷新/复用 token（提前于过期刷新）
                now = time.time()
                if not self._token or (now - self._token_acquired_at > settings.KRAKEN_WS_TOKEN_TTL_SEC):
                    token_resp = await self._client.get_ws_token()
                    if token_resp.get("error"):
                        raise RuntimeError(f"GetWebSocketsToken error: {token_resp['error']}")
                    token = (token_resp.get("result") or {}).get("token")
                    if not token:
                        raise RuntimeError("GetWebSocketsToken returned no token")
                    self._token = token
                    self._token_acquired_at = now

                async with websockets.connect(settings.KRAKEN_WS_AUTH_URL) as ws:
                    await self._subscribe_open_orders(ws, self._token)
                    await self._subscribe_own_trades(ws, self._token)

                    async for raw in ws:
                        try:
                            msg = json.loads(raw)
                        except Exception:
                            continue
                        if isinstance(msg, dict) and msg.get("event") == "heartbeat":
                            continue
                        if isinstance(msg, dict) and msg.get("event") == "subscriptionStatus":
                            # 可记录订阅成功/失败
                            continue
                        await self._handle_private_message(msg)
            except Exception as e:
                import logging as _logging
                _logging.getLogger(__name__).info(f"WS listener error: {e}. Reconnecting in {self._reconnect_backoff}s...")
                await asyncio.sleep(self._reconnect_backoff)


async def main() -> None:
    listener = KrakenWSListener()
    await listener.run_forever()


if __name__ == "__main__":
    asyncio.run(main())


