from fastapi import FastAPI, HTTPException, Query
import time
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
import uuid
import json
import redis
import logging
from enum import Enum
import httpx

from app.config import settings
from app.ledger import ledger_instance as ledger
from app.models import TradePlan, TakeProfitTarget, StreamAction

app = FastAPI(title="Trading Service (Virtual)")
logger = logging.getLogger(__name__)

_redis = redis.Redis.from_url(settings.REDIS_URL, decode_responses=True)
_stream_key = settings.REDIS_STREAM_KEY


def _push_to_stream(message: dict) -> str:
    req_id = uuid.uuid4().hex
    envelope = {"request_id": req_id, **message}
    # 多字段写入：顶层字段直接写；嵌套结构（如 plan/new_take_profits）序列化为 JSON 字符串
    fields: dict[str, str] = {}
    for k, v in envelope.items():
        # 跳过 None，避免出现空字符串导致验证失败（例如 userref）
        if v is None:
            continue
        # 统一规范化：Enum → value；嵌套结构 → JSON；其余转 str
        if isinstance(v, Enum):
            fields[k] = v.value
        elif k in ("plan", "new_take_profits"):
            fields[k] = json.dumps(v)
        else:
            fields[k] = str(v)
    _redis.xadd(_stream_key, fields)
    logger.info(f"[API] Enqueued to stream key={_stream_key} request_id={req_id} action={message.get('action')} symbol={message.get('symbol')} userref={message.get('userref')}")
    return req_id


@app.post("/orders/add", status_code=202)
def orders_add(plan: TradePlan, userref: int | None = None):
    """
    短测入口：将 TradePlan 封装为 Stream add 消息。
    实际生产建议直接由上游向 Stream 写入。
    """
    payload = plan.model_dump()
    if userref is not None:
        payload["userref"] = userref
    msg = {"action": StreamAction.add, "plan": payload, "userref": userref, "symbol": plan.symbol}
    request_id = _push_to_stream(msg)
    return {"message": "enqueued", "request_id": request_id}


@app.post("/orders/amend", status_code=202)
def orders_amend(
    userref: int,
    new_entry_price: float | None = None,
    new_stop_loss_price: float | None = None,
    new_tp1_price: float | None = None,
    new_tp2_price: float | None = None,
    new_take_profits: list[TakeProfitTarget] | None = None,
):
    if not any([new_entry_price, new_stop_loss_price, new_tp1_price, new_tp2_price, new_take_profits]):
        raise HTTPException(status_code=400, detail="nothing to amend")
    msg = {
        "action": StreamAction.amend,
        "userref": userref,
        "symbol": None,
        "new_entry_price": new_entry_price,
        "new_stop_loss_price": new_stop_loss_price,
        "new_tp1_price": new_tp1_price,
        "new_tp2_price": new_tp2_price,
        "new_take_profits": [tp.model_dump() for tp in (new_take_profits or [])],
    }
    request_id = _push_to_stream(msg)
    return {"message": "enqueued", "request_id": request_id}


@app.post("/orders/cancel", status_code=202)
def orders_cancel(userref: int):
    msg = {"action": StreamAction.cancel, "userref": userref, "symbol": None}
    request_id = _push_to_stream(msg)
    return {"message": "enqueued", "request_id": request_id}


@app.on_event("startup")
async def startup_event():
    logger.info("Kraken Trading Service API started (Stream test endpoints enabled).")


# ---------------------- kraken-filter API（从 Redis 读取，与 kraken_service 对齐，并叠加台账） ----------------------
@app.get("/kraken-filter")
async def kraken_filter_api():
    try:
        # 读取 Redis 快照
        main_hash_key = "kraken_data:main"
        trade_hash_key = "kraken_data:trade_history"
        if not _redis.exists(main_hash_key):
            raise HTTPException(status_code=503, detail="No Kraken data available in Redis (kraken_service).")
        main_data = _redis.hgetall(main_hash_key)
        open_orders = json.loads(main_data.get("open_orders", "{}") or "{}")
        account_balance = json.loads(main_data.get("account_balance", "{}") or "{}")
        trade_balance_raw = json.loads(main_data.get("trade_balance", "{}") or "{}")

        trade_map = {}
        if _redis.exists(trade_hash_key):
            trade_map = _redis.hgetall(trade_hash_key)

        # 不接收 symbol：直接返回 Redis 中的所有交易历史
        filtered_trade_history: dict[str, list] = {}
        for key, trades_json in (trade_map or {}).items():
            try:
                filtered_trade_history[key] = json.loads(trades_json)
            except Exception:
                continue

        # 交易余额重命名（与 kraken_service 对齐）
        trade_balance = {
            "equivalent_balance": trade_balance_raw.get("eb", ""),
            "trade_balance": trade_balance_raw.get("tb", ""),
            "margin": trade_balance_raw.get("m", ""),
            "unrealized_pnl": trade_balance_raw.get("n", ""),
            "cost_basis": trade_balance_raw.get("c", ""),
            "valuation": trade_balance_raw.get("v", ""),
            "equity": trade_balance_raw.get("e", ""),
            "free_margin": trade_balance_raw.get("mf", ""),
            "margin_level": trade_balance_raw.get("ml", ""),
            "unexecuted_value": trade_balance_raw.get("uv", ""),
        }

        # 叠加台账信息到 open_orders（open_orders 是按 pair 分组的 dict[{...}]）
        try:
            trades = ledger.get_all_trades()
            by_userref = {}
            by_entry = {}
            by_sl = {}
            by_symbol: dict[str, list] = {}
            for t in trades:
                if getattr(t, "userref", None) is not None:
                    by_userref[str(t.userref)] = t
                if getattr(t, "entry_txid", None):
                    by_entry[str(t.entry_txid)] = t
                if getattr(t, "stop_loss_txid", None):
                    by_sl[str(t.stop_loss_txid)] = t
                by_symbol.setdefault(t.symbol, []).append(t)

            used_userrefs: set[str] = set()
            for pair, lst in list((open_orders or {}).items()):
                new_list = []
                for o in lst or []:
                    oid = str(o.get("order_id") or "")
                    uref = o.get("userref")
                    t = None
                    if oid and oid in by_entry:
                        t = by_entry[oid]
                    elif oid and oid in by_sl:
                        t = by_sl[oid]
                    elif uref is not None and str(uref) in by_userref:
                        t = by_userref[str(uref)]
                    # 回退匹配：按 symbol + 价格接近且状态为 PENDING，且未被占用（按 userref 去重）
                    if not t:
                        try:
                            order_price = float(o.get("price") or 0.0)
                        except Exception:
                            order_price = None
                        cands = [ct for ct in by_symbol.get(pair, []) if getattr(ct, "status", None) == "PENDING" and str(getattr(ct, "userref", None)) not in used_userrefs]
                        if order_price is not None and cands:
                            def _price_close(x: float, y: float, tol: float = 1e-6) -> bool:
                                return abs(float(x) - float(y)) <= tol * max(1.0, abs(float(y)))
                            for cand in cands:
                                try:
                                    if _price_close(order_price, float(getattr(cand, "entry_price", 0.0))):
                                        t = cand
                                        break
                                except Exception:
                                    continue
                    # 分组与角色标记（便于一眼识别属于同一套单）
                    group_id = None
                    order_role = "other"
                    tp_index = None
                    if t:
                        # 不再暴露内部 trade_id 与 stop_loss_txid
                        o["take_profits"] = [tp.model_dump() for tp in (t.take_profits or [])]
                        o["remaining_size"] = t.remaining_size
                        o["sl_price"] = getattr(t, "stop_loss_price", None)
                        o["trade_status"] = t.status
                        # 摘要字段（便于直观展示 TP1/TP2）
                        try:
                            if t.take_profits:
                                tp1 = t.take_profits[0]
                                o["tp1_price"] = tp1.price
                                o["tp1_pct"] = tp1.percentage_to_sell
                            if len(t.take_profits) > 1:
                                tp2 = t.take_profits[1]
                                o["tp2_price"] = tp2.price
                                o["tp2_pct"] = tp2.percentage_to_sell
                        except Exception:
                            pass
                        used_userrefs.add(str(getattr(t, "userref", "")))
                        group_id = str(getattr(t, "userref", "")) if getattr(t, "userref", None) is not None else None
                        # 角色：entry / stop_loss / tp1 / tp2 / other
                        try:
                            if getattr(t, "entry_txid", None) and oid == t.entry_txid:
                                order_role = "entry"
                            elif getattr(t, "stop_loss_txid", None) and oid == t.stop_loss_txid:
                                order_role = "stop_loss"
                            else:
                                op = float(o.get("price") or 0.0)
                                if t.take_profits and len(t.take_profits) >= 1 and abs(op - float(t.take_profits[0].price)) <= 1e-6 * max(1.0, abs(float(t.take_profits[0].price))):
                                    order_role = "tp1"
                                    tp_index = 1
                                if t.take_profits and len(t.take_profits) >= 2 and abs(op - float(t.take_profits[1].price)) <= 1e-6 * max(1.0, abs(float(t.take_profits[1].price))):
                                    order_role = "tp2"
                                    tp_index = 2
                        except Exception:
                            pass
                    else:
                        # 无法匹配到台账时，用 userref 兜底分组
                        group_id = str(uref) if uref is not None else None
                    if group_id is not None:
                        o["group_id"] = group_id
                    o["order_role"] = order_role
                    if tp_index is not None:
                        o["tp_index"] = tp_index
                    new_list.append(o)
                open_orders[pair] = new_list
        except Exception:
            pass

        return {
            "balance": account_balance,
            "trade_balance": trade_balance,
            "open_orders": open_orders,
            "trade_history": filtered_trade_history,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
