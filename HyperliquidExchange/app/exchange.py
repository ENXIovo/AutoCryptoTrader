"""
Order Management - 单职责：订单管理代理层
完全依赖 Hyperliquid API，不维护本地缓存
"""
import logging
from typing import Dict, Any

from app.hyperliquid_client import hl_client

logger = logging.getLogger(__name__)


class OrderManager:
    """
    订单管理器 - 纯代理模式
    单职责：直接代理 Hyperliquid API，不维护任何本地状态
    """
    
    def __init__(self):
        # 完全代理模式，不需要初始化任何缓存
        logger.info("[OrderManager] Initialized in proxy mode (no local cache)")
    
    async def place_order(self, order_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        下单 - 直接代理 Hyperliquid API
        order_data: {coin, is_buy, sz, limit_px, order_type, reduce_only, stop_loss, take_profit}
        """
        coin = order_data.get("coin")
        is_buy = order_data.get("is_buy")
        sz = float(order_data.get("sz", 0))
        limit_px = float(order_data.get("limit_px", 0))
        order_type = order_data.get("order_type", {"limit": {"tif": "Gtc"}})
        reduce_only = order_data.get("reduce_only", False)
        stop_loss = order_data.get("stop_loss")
        take_profit = order_data.get("take_profit")
        
        # 如果有 TPSL，使用 bulk_orders 和 grouping
        if stop_loss and take_profit:
            orders = [
                {
                    "coin": coin,
                    "is_buy": is_buy,
                    "sz": sz,
                    "limit_px": limit_px,
                    "order_type": order_type,
                    "reduce_only": reduce_only,
                },
                {
                    "coin": coin,
                    "is_buy": not is_buy,
                    "sz": sz,
                    "limit_px": float(take_profit.get("price", 0)),
                    "order_type": {
                        "trigger": {
                            "isMarket": True,
                            "triggerPx": float(take_profit.get("price", 0)),
                            "tpsl": "tp",
                        }
                    },
                    "reduce_only": True,
                },
                {
                    "coin": coin,
                    "is_buy": not is_buy,
                    "sz": sz,
                    "limit_px": float(stop_loss.get("price", 0)),
                    "order_type": {
                        "trigger": {
                            "isMarket": True,
                            "triggerPx": float(stop_loss.get("price", 0)),
                            "tpsl": "sl",
                        }
                    },
                    "reduce_only": True,
                },
            ]
            result = hl_client.bulk_orders(orders, grouping="normalTpsl")
        else:
            # 普通订单
            result = hl_client.place_order(coin, is_buy, sz, limit_px, order_type, reduce_only)
        
        # 直接返回 Hyperliquid 的原始响应，不维护任何缓存
        if result.get("status") == "ok":
            logger.info(f"[OrderManager] Order placed successfully: coin={coin}, side={'buy' if is_buy else 'sell'}")
        else:
            logger.error(f"[OrderManager] Order placement failed: {result}")
        
        return result
    
    async def cancel_order(self, cancel_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        取消订单 - 直接代理 Hyperliquid API
        cancel_data: {coin, oid}
        注意：只支持通过 oid 取消，不支持 userref（完全依赖 Hyperliquid）
        """
        coin = cancel_data.get("coin")
        oid = cancel_data.get("oid")
        
        if not coin or not oid:
            return {"status": "err", "response": "coin and oid are required"}
        
        # 直接调用 Hyperliquid SDK，不依赖任何缓存
        result = hl_client.cancel_order(coin, int(oid))
        
        if result.get("status") == "ok":
            logger.info(f"[OrderManager] Order canceled: oid={oid}, coin={coin}")
        else:
            logger.error(f"[OrderManager] Order cancellation failed: {result}")
        
        return result
    
    async def modify_order(self, modify_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        修改订单 - 直接代理 Hyperliquid API
        modify_data: {oid, coin, is_buy, sz, limit_px, order_type}
        所有字段必须提供（符合 Hyperliquid SDK 要求）
        """
        oid = modify_data.get("oid")
        coin = modify_data.get("coin")
        is_buy = modify_data.get("is_buy")
        sz = float(modify_data.get("sz", 0))
        limit_px = float(modify_data.get("limit_px", 0))
        order_type = modify_data.get("order_type", {"limit": {"tif": "Gtc"}})
        
        # 直接调用 Hyperliquid SDK，不依赖任何缓存
        result = hl_client.modify_order(oid, coin, is_buy, sz, limit_px, order_type)
        
        if result.get("status") == "ok":
            logger.info(f"[OrderManager] Order modified: oid={oid}, coin={coin}")
        else:
            logger.error(f"[OrderManager] Order modification failed: {result}")
        
        return result


# Singleton
order_manager = OrderManager()
