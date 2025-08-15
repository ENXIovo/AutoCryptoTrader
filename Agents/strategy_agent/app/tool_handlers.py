from .tool_router import NewsClient, KrakenClient, DataClient
from .config import settings
from .rrr import calc_rrr_batch
import json
import redis
from celery import Celery
from datetime import datetime, timezone, timedelta

"""
此模块将工具名称映射到可以执行的具体函数。为了保持职责分离，
StrategyAgent 本身不会直接处理其他服务的逻辑，而是通过调用
外部 HTTP API 来获得数据。新增的 ``kraken_filter`` 和 ``gpt_latest``
工具分别调用 KrakenService 的 ``/kraken-filter`` 端点和
DataCollector 的 ``/gpt-latest/{symbol}`` 端点。
"""

# 实例化路由器
news_client = NewsClient(settings.news_service_url)
kraken_client = KrakenClient(settings.trading_url)
data_client = DataClient(settings.data_service_url)

def _getTopNews_fixed(**_ignored) -> list[dict]:
    return news_client.getTopNews(limit=settings.news_top_limit, period=None)

def calcRRR(**kwargs) -> dict:
    """
    纯数学 RRR 批量计算器。
    期望参数: { "cases": [ { "entry":..., "stop":..., "tp1":..., "tp2":... }, ... ] }
    """
    cases = kwargs.get("cases") or []
    if not isinstance(cases, list):
        raise ValueError("calcRRR expects 'cases' as a list")
    return calc_rrr_batch(cases)

TOOL_HANDLERS = {
    "getTopNews": _getTopNews_fixed,
    "getAccountInfo": kraken_client.getAccountInfo,
    "getKlineIndicators": data_client.getKlineIndicators,
    "calcRRR": calcRRR,
    # New trading tools
    "addOrder": None,
    "amendOrder": None,
    "cancelOrder": None,
}

# ---- Redis stream pusher helpers ----
_r = redis.Redis.from_url(settings.redis_url, decode_responses=True)
_stream_key = settings.trade_actions_stream_key

def _push_stream(message: dict) -> str:
    # flatten: nested dicts to JSON strings for 'plan' and 'new_take_profits'
    envelope = {**message}
    if "plan" in envelope and isinstance(envelope["plan"], dict):
        envelope["plan"] = json.dumps(envelope["plan"])
    if "new_take_profits" in envelope and isinstance(envelope["new_take_profits"], list):
        envelope["new_take_profits"] = json.dumps(envelope["new_take_profits"])
    return _r.xadd(_stream_key, {k: str(v) for k, v in envelope.items() if v is not None})

def addOrder(**kwargs) -> dict:
    plan = {
        "symbol": kwargs.get("symbol"),
        "side": kwargs.get("side"),
        "entry_price": kwargs.get("entry_price"),
        "position_size": kwargs.get("position_size"),
        "stop_loss_price": kwargs.get("stop_loss_price"),
        "take_profits": kwargs.get("take_profits"),
        "entry_ordertype": kwargs.get("entry_ordertype", "market"),
        # map post_only -> oflags ["post"] for KrakenTradingSpot executor (which serializes list)
        "oflags": ["post"] if kwargs.get("post_only") else None,
        "userref": kwargs.get("userref"),
    }
    msg = {"action": "add", "symbol": plan["symbol"], "plan": plan, "userref": plan.get("userref")}
    xid = _push_stream(msg)
    return {"enqueued": True, "stream_id": xid}

def amendOrder(**kwargs) -> dict:
    msg = {
        "action": "amend",
        "order_id": kwargs.get("order_id"),
        "trade_id": kwargs.get("trade_id"),
        "new_entry_price": kwargs.get("new_entry_price"),
        "new_stop_loss_price": kwargs.get("new_stop_loss_price"),
        "new_tp1_price": kwargs.get("new_tp1_price"),
        "new_tp2_price": kwargs.get("new_tp2_price"),
        "new_take_profits": kwargs.get("new_take_profits"),
    }
    xid = _push_stream(msg)
    return {"enqueued": True, "stream_id": xid}

def cancelOrder(**kwargs) -> dict:
    msg = {"action": "cancel", "order_id": kwargs.get("order_id"), "trade_id": kwargs.get("trade_id")}
    xid = _push_stream(msg)
    return {"enqueued": True, "stream_id": xid}

# bind handlers
TOOL_HANDLERS["addOrder"] = addOrder
TOOL_HANDLERS["amendOrder"] = amendOrder
TOOL_HANDLERS["cancelOrder"] = cancelOrder


# ---- Meeting reschedule handler (CTO only) ----
def _celery_client() -> Celery:
    return Celery(
        "strategy_tasks",
        broker=settings.celery_broker_url,
        backend=settings.celery_result_backend,
    )


def rescheduleMeeting(**kwargs) -> dict:
    """
    Schedule a one-off strategy meeting after a short countdown (minutes).
    Constraints: countdown_minutes in [5, 180]. Always returns the scheduled UTC ISO time.
    Regardless of calling this tool, the system also runs at a fixed 4-hour cadence at minute 05 UTC daily.
    """
    countdown_minutes = kwargs.get("countdown_minutes")
    reason = kwargs.get("reason")
    if not isinstance(countdown_minutes, int):
        raise ValueError("countdown_minutes must be an integer (minutes)")
    if countdown_minutes < 5 or countdown_minutes > 180:
        raise ValueError("countdown_minutes must be between 5 and 180 minutes (inclusive)")
    if not isinstance(reason, str) or not reason.strip():
        raise ValueError("reason is required and must be a non-empty string")

    now = datetime.now(timezone.utc)
    eta = now + timedelta(minutes=countdown_minutes)

    app = _celery_client()
    # Send by task name to avoid import cycles; route to the same queue as beat uses
    app.send_task(
        "app.tasks.run_strategy",
        args=(),
        kwargs={},
        countdown=countdown_minutes * 60,
        queue="auto_trade_queue",
    )

    # Optional: audit log
    try:
        _r.xadd(
            "strategy:reschedules",
            {
                "requested_at": now.isoformat(),
                "scheduled_for": eta.isoformat(),
                "countdown_minutes": str(countdown_minutes),
                "reason": reason,
            },
        )
    except Exception:
        pass

    return {
        "scheduled": True,
        "countdown_minutes": countdown_minutes,
        "scheduled_for_utc": eta.isoformat(),
        "note": "This only overrides the NEXT meeting. The system also runs at a fixed 4-hour cadence at :05 UTC.",
    }

TOOL_HANDLERS["rescheduleMeeting"] = rescheduleMeeting
