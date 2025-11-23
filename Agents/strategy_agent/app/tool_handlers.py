import requests
import logging
from datetime import datetime, timezone, timedelta
from .rrr import calc_rrr_batch
from .config import settings
from .tool_router import NewsClient, DataClient, ExchangeClient

logger = logging.getLogger(__name__)

# 全局回测时间戳（用于回测模式）
_backtest_timestamp: Optional[float] = None

def set_backtest_timestamp(timestamp: Optional[float]) -> None:
    """设置回测时间戳（用于回测模式）"""
    global _backtest_timestamp
    _backtest_timestamp = timestamp

def get_backtest_timestamp() -> Optional[float]:
    """获取回测时间戳"""
    return _backtest_timestamp

# 实例化路由器（延迟初始化，支持回测模式）
def _get_clients():
    """获取客户端实例（支持回测模式）"""
    return (
        NewsClient(settings.news_service_url, backtest_timestamp=_backtest_timestamp),
        DataClient(settings.data_service_url, backtest_timestamp=_backtest_timestamp),
        ExchangeClient(settings.trading_url)
    )

# 默认实例（实时模式）
news_client, data_client, exchange_client = _get_clients()

def _getTopNews_fixed(**_ignored) -> list[dict]:
    # 每次调用时获取最新的客户端（支持回测模式）
    news_client, _, _ = _get_clients()
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

def _getAccountInfo(**_ignored) -> dict:
    """Calls POST /info with clearinghouseState"""
    try:
        # Use the client wrapper
        return exchange_client.getAccountInfo()
    except Exception as e:
        return {"error": str(e)}

def placeOrder(**kwargs) -> dict:
    """
    Calls POST /exchange/order with required TPSL support (OCO format)
    
    回测模式：在回测模式下，订单会被收集而不是立即执行。
    订单信息会从 tool_calls 中提取，然后在回测编排器中统一处理。
    """
    # 检查是否在回测模式
    backtest_timestamp = get_backtest_timestamp()
    
    coin = kwargs.get("coin")
    limit_px = float(kwargs.get("limit_px") or 0.0)
    
    payload = {
        "coin": coin,
        "is_buy": kwargs.get("is_buy"),
        "sz": float(kwargs.get("sz") or 0.0),
        "limit_px": limit_px,
        "reduce_only": kwargs.get("reduce_only", False)
    }
    
    # TPSL parameters are required
    stop_loss = kwargs.get("stop_loss")
    if stop_loss is None or not isinstance(stop_loss, dict):
        return {"status": "err", "response": "stop_loss is required and must be an object with 'price' field"}
    payload["stop_loss"] = stop_loss
    
    take_profit = kwargs.get("take_profit")
    if take_profit is None or not isinstance(take_profit, dict):
        return {"status": "err", "response": "take_profit is required and must be an object with 'price' field"}
    payload["take_profit"] = take_profit
    
    # 回测模式：返回模拟成功响应，订单会从 tool_calls 中提取
    if backtest_timestamp:
        logger.info(f"[placeOrder] Backtest mode: Order recorded (not executed) - {coin} {'BUY' if kwargs.get('is_buy') else 'SELL'} {kwargs.get('sz')} @ {limit_px}")
        return {
            "status": "ok",
            "response": {
                "data": {
                    "statuses": [{
                        "resting": {
                            "oid": hash(f"{backtest_timestamp}_{coin}_{kwargs.get('is_buy')}") % 1000000000
                        }
                    }]
                },
                "backtest_mode": True,
                "note": "Order recorded for backtest execution"
            }
        }
    
    # 生产模式：实际调用 exchange
    # Construct internal HL-style order_type
    if limit_px <= 0:
        payload["order_type"] = {"market": {}}
    else:
        payload["order_type"] = {"limit": {"tif": "Gtc"}}
        
    try:
        resp = requests.post(f"{settings.trading_url}/exchange/order", json=payload, timeout=5)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        return {"status": "err", "response": str(e)}

def cancelOrder(**kwargs) -> dict:
    """
    Calls POST /exchange/cancel
    
    回测模式：在回测模式下，取消订单会被记录但不会立即执行。
    """
    # 检查是否在回测模式
    backtest_timestamp = get_backtest_timestamp()
    
    if backtest_timestamp:
        logger.info(f"[cancelOrder] Backtest mode: Cancel order recorded (not executed) - oid={kwargs.get('oid')}")
        return {
            "status": "ok",
            "response": {"data": "Order cancel recorded for backtest", "backtest_mode": True}
        }
    
    # 生产模式：实际调用 exchange
    payload = {
        "coin": kwargs.get("coin"),
        "oid": kwargs.get("oid")
    }
    try:
        resp = requests.post(f"{settings.trading_url}/exchange/cancel", json=payload, timeout=5)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        return {"status": "err", "response": str(e)}

def rescheduleMeeting(**kwargs) -> dict:
    """
    调度一次性的策略会议（覆盖下一次会议时间）
    使用 Celery 的 apply_async 来延迟执行任务
    """
    countdown_minutes = kwargs.get("countdown_minutes", 60)
    reason = kwargs.get("reason", "No reason provided")
    
    # 验证参数
    if not isinstance(countdown_minutes, int) or countdown_minutes < 5 or countdown_minutes > 180:
        return {
            "status": "err",
            "response": f"countdown_minutes must be between 5 and 180, got {countdown_minutes}"
        }
    
    try:
        # 导入 tasks 模块（延迟导入避免循环依赖）
        from .tasks import run_strategy
        
        # 计算执行时间（UTC）
        execute_time = datetime.now(timezone.utc) + timedelta(minutes=countdown_minutes)
        
        # 使用 Celery 的 apply_async 调度任务
        result = run_strategy.apply_async(
            eta=execute_time,
            queue="auto_trade_queue"
        )
        
        return {
            "status": "ok",
            "response": {
                "message": f"Meeting rescheduled successfully",
                "scheduled_time_utc": execute_time.isoformat(),
                "countdown_minutes": countdown_minutes,
                "reason": reason,
                "task_id": result.id,
                "note": "This is a one-off override. The regular 4-hour cadence will resume after this meeting."
            }
        }
    except Exception as e:
        logger.error(f"Failed to reschedule meeting: {e}")
        return {
            "status": "err",
            "response": f"Failed to reschedule meeting: {str(e)}"
        }

def _getKlineIndicators(symbol: str, **_ignored) -> dict:
    """Wrapper for getKlineIndicators (支持回测模式)"""
    _, data_client, _ = _get_clients()
    return data_client.getKlineIndicators(symbol)

# Map handlers
TOOL_HANDLERS = {
    "getTopNews": _getTopNews_fixed,
    "getKlineIndicators": _getKlineIndicators,
    "getAccountInfo": _getAccountInfo,
    "placeOrder": placeOrder,
    "cancelOrder": cancelOrder,
    "calcRRR": calcRRR,  # 添加 calcRRR
    "rescheduleMeeting": rescheduleMeeting,  # 添加 rescheduleMeeting
}
