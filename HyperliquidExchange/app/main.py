"""
FastAPI Application - 单职责：API 代理层
直接透传 Hyperliquid API 格式，保持一致性
"""
import logging
from typing import Dict, Any

from fastapi import FastAPI, HTTPException

from app.exchange import order_manager
from app.hyperliquid_client import hl_client
from app.models import (
    PlaceOrderRequest,
    ModifyOrderRequest,
    CancelOrderRequest,
    UpdateLeverageRequest,
    UpdateIsolatedMarginRequest,
)

logger = logging.getLogger(__name__)
app = FastAPI(title="Hyperliquid Exchange API Proxy")

# ---------- API Endpoints (代理 Hyperliquid API) ----------

@app.post("/exchange/order")
async def place_order(order: PlaceOrderRequest) -> Dict[str, Any]:
    """
    Place order - 直接代理 Hyperliquid API
    请求格式与 Hyperliquid SDK 一致
    返回格式与 Hyperliquid API 一致: {"status": "ok", "response": {"data": {"statuses": [...]}}}
    """
    try:
        order_data = {
            "coin": order.coin,
            "is_buy": order.is_buy,
            "sz": order.sz,
            "limit_px": order.limit_px,
            "order_type": order.order_type,
            "reduce_only": order.reduce_only,
            "stop_loss": order.stop_loss,
            "take_profit": order.take_profit,
        }
        
        # 直接返回 Hyperliquid 的原始响应格式
        result = await order_manager.place_order(order_data)
        return result
        
    except Exception as e:
        logger.error(f"Order placement failed: {e}")
        return {"status": "err", "response": str(e)}

@app.post("/exchange/cancel")
async def cancel_order(req: CancelOrderRequest) -> Dict[str, Any]:
    """
    Cancel order - 直接代理 Hyperliquid API
    返回格式与 Hyperliquid API 一致: {"status": "ok", "response": {...}}
    """
    try:
        cancel_data = {
            "coin": req.coin,
            "oid": req.oid,
        }
        
        # 直接返回 Hyperliquid 的原始响应格式
        result = await order_manager.cancel_order(cancel_data)
        return result
        
    except Exception as e:
        logger.error(f"Order cancellation failed: {e}")
        return {"status": "err", "response": str(e)}

@app.post("/exchange/modify")
async def modify_order(req: ModifyOrderRequest) -> Dict[str, Any]:
    """
    Modify order - 直接代理 Hyperliquid API
    返回格式与 Hyperliquid API 一致: {"status": "ok", "response": {...}}
    
    注意：所有字段必须提供（符合 Hyperliquid SDK 要求）
    """
    try:
        modify_data = {
            "oid": req.oid,
            "coin": req.coin,
            "is_buy": req.is_buy,
            "sz": req.sz,
            "limit_px": req.limit_px,
            "order_type": req.order_type,
        }
        
        # 直接返回 Hyperliquid 的原始响应格式
        result = await order_manager.modify_order(modify_data)
        return result
        
    except Exception as e:
        logger.error(f"Order modification failed: {e}")
        return {"status": "err", "response": str(e)}

@app.post("/info")
async def get_info(req: Dict[str, Any]) -> Dict[str, Any]:
    """
    Info endpoint - 代理 Hyperliquid user_state 和 open_orders
    返回格式与 Hyperliquid API 一致
    """
    req_type = req.get("type")
    
    if req_type == "metaAndAssetCtxs":
        # 从 Hyperliquid API 获取 universe 信息
        try:
            meta = hl_client.get_meta()
            # 提取 universe 信息
            universe = []
            for asset in meta.get("universe", []):
                universe.append({
                    "name": asset.get("name", ""),
                    "szDecimals": asset.get("szDecimals", 0),
                    "maxLeverage": asset.get("maxLeverage", {}).get("value", 50) if isinstance(asset.get("maxLeverage"), dict) else 50,
                })
            return {"universe": universe}
        except Exception as e:
            logger.error(f"Failed to get universe from Hyperliquid: {e}")
            # Fallback to basic list
            return {
                "universe": [
                    {"name": "BTC", "szDecimals": 5, "maxLeverage": 50},
                    {"name": "ETH", "szDecimals": 4, "maxLeverage": 50}
                ]
            }
        
    if req_type == "clearinghouseState":
        # 从 Hyperliquid API 获取用户状态
        try:
            user_state = hl_client.get_user_state()
            margin_summary = user_state.get("marginSummary", {})
            asset_positions = user_state.get("assetPositions", [])
            
            # 从 Hyperliquid API 获取未完成订单（实时）
            open_orders_raw = hl_client.get_open_orders()
            open_orders = []
            for order in open_orders_raw:
                open_orders.append({
                    "oid": order.get("oid"),
                    "coin": order.get("coin", ""),
                    "side": order.get("side", "B"),  # "B" or "A"
                    "limitPx": order.get("limitPx", "0"),
                    "sz": order.get("sz", "0"),
                    "timestamp": order.get("timestamp", 0),
                })
            
            return {
                "marginSummary": {
                    "accountValue": str(margin_summary.get("accountValue", "0.0")),
                    "totalMarginUsed": str(margin_summary.get("totalMarginUsed", "0.0"))
                },
                "crossMarginSummary": {
                    "accountValue": str(margin_summary.get("accountValue", "0.0"))
                },
                "assetPositions": asset_positions,
                "openOrders": open_orders
            }
        except Exception as e:
            logger.error(f"Failed to get user state from Hyperliquid: {e}")
            return {
                "marginSummary": {
                    "accountValue": "0.0",
                    "totalMarginUsed": "0.0"
                },
                "crossMarginSummary": {
                    "accountValue": "0.0"
                },
                "assetPositions": [],
                "openOrders": []
            }
        
    return {"status": "err", "response": "Unknown info type"}

@app.post("/exchange/leverage")
async def update_leverage(req: UpdateLeverageRequest) -> Dict[str, Any]:
    """
    Update leverage - 设置杠杆倍数
    返回格式与 Hyperliquid API 一致: {"status": "ok", "response": {...}}
    
    Payload:
    {
        "leverage": 21,  # 杠杆倍数（如 21 表示 21x）
        "coin": "ETH",   # 交易对（仅支持 perps）
        "is_cross": true  # true 为全仓，false 为逐仓
    }
    """
    try:
        result = hl_client.update_leverage(req.leverage, req.coin, req.is_cross)
        return result
    except Exception as e:
        logger.error(f"Leverage update failed: {e}")
        return {"status": "err", "response": str(e)}

@app.post("/exchange/isolated-margin")
async def update_isolated_margin(req: UpdateIsolatedMarginRequest) -> Dict[str, Any]:
    """
    Update isolated margin - 调整隔离保证金
    返回格式与 Hyperliquid API 一致: {"status": "ok", "response": {...}}
    
    Payload:
    {
        "margin": 1.0,   # 保证金金额（USD，可以为负数以减少保证金）
        "coin": "ETH"    # 交易对（仅支持 perps）
    }
    """
    try:
        result = hl_client.update_isolated_margin(req.margin, req.coin)
        return result
    except Exception as e:
        logger.error(f"Isolated margin update failed: {e}")
        return {"status": "err", "response": str(e)}
