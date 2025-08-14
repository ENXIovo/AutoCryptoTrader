from fastapi import FastAPI, HTTPException
import uuid
import json
import redis
import logging
from enum import Enum

from app.config import settings
from app.models import TradePlan, TakeProfitTarget, StreamAction

app = FastAPI(title="Kraken Trading Service")
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
def orders_amend(order_id: str | None = None, trade_id: str | None = None, userref: int | None = None, new_stop_loss_price: float | None = None, new_take_profits: list[TakeProfitTarget] | None = None):
    if new_stop_loss_price is None and not new_take_profits:
        raise HTTPException(status_code=400, detail="nothing to amend")
    msg = {
        "action": StreamAction.amend,
        "order_id": order_id,
        "trade_id": trade_id,
        "userref": userref,
        "symbol": None,
        "new_stop_loss_price": new_stop_loss_price,
        "new_take_profits": [tp.model_dump() for tp in (new_take_profits or [])],
    }
    request_id = _push_to_stream(msg)
    return {"message": "enqueued", "request_id": request_id}


@app.post("/orders/cancel", status_code=202)
def orders_cancel(order_id: str | None = None, trade_id: str | None = None, userref: int | None = None):
    msg = {"action": StreamAction.cancel, "order_id": order_id, "trade_id": trade_id, "userref": userref, "symbol": None}
    request_id = _push_to_stream(msg)
    return {"message": "enqueued", "request_id": request_id}


@app.on_event("startup")
async def startup_event():
    logger.info("Kraken Trading Service API started (Stream test endpoints enabled).")
