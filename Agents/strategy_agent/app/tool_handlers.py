import requests
import logging
from .rrr import calc_rrr_batch
from .config import settings
from .tool_router import NewsClient, DataClient, ExchangeClient

logger = logging.getLogger(__name__)

# 实例化路由器
news_client = NewsClient(settings.news_service_url)
data_client = DataClient(settings.data_service_url)
exchange_client = ExchangeClient(settings.trading_url)

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

def _getAccountInfo(**_ignored) -> dict:
    """Calls POST /info with clearinghouseState"""
    try:
        # Use the client wrapper
        return exchange_client.getAccountInfo()
    except Exception as e:
        return {"error": str(e)}

def placeOrder(**kwargs) -> dict:
    """Calls POST /exchange/order with required TPSL support (OCO format)"""
    # Hyperliquid-Lite expects: {coin, is_buy, sz, limit_px, order_type: {...}}
    # Schema: {coin, is_buy, sz, limit_px, stop_loss: {price}, take_profit: {price}}
    # We map 'limit_px=0' -> Market
    
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
    """Calls POST /exchange/cancel"""
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

# Map handlers
TOOL_HANDLERS = {
    "getTopNews": _getTopNews_fixed,
    "getKlineIndicators": data_client.getKlineIndicators,
    "getAccountInfo": _getAccountInfo,
    "placeOrder": placeOrder,
    "cancelOrder": cancelOrder
}
