"""
Matching Engine - 单职责：非实时撮合引擎
基于1分钟K线数据，支持时间轴加速
"""
import logging
import time
from typing import List, Optional, Dict, Any
from app.models import VirtualOrder, OHLC

logger = logging.getLogger(__name__)


class MatchingEngine:
    """
    非实时撮合引擎
    - 基于1分钟K线数据
    - 支持时间轴加速
    - 完全可控的订单执行
    """
    
    def __init__(self):
        """初始化撮合引擎"""
        self.orders: Dict[str, VirtualOrder] = {}  # txid -> order
        logger.info("[MatchingEngine] Initialized")
    
    def add_order(self, order: VirtualOrder) -> None:
        """
        添加订单到撮合引擎
        
        Args:
            order: 订单
        """
        self.orders[order.txid] = order
        logger.info(f"[MatchingEngine] Added order {order.txid}: {order.type} {order.volume} {order.pair} @ {order.price}")
    
    def remove_order(self, txid: str) -> Optional[VirtualOrder]:
        """
        移除订单
        
        Args:
            txid: 订单ID
            
        Returns:
            被移除的订单，如果不存在则返回None
        """
        return self.orders.pop(txid, None)
    
    def get_order(self, txid: str) -> Optional[VirtualOrder]:
        """
        获取订单
        
        Args:
            txid: 订单ID
            
        Returns:
            订单，如果不存在则返回None
        """
        return self.orders.get(txid)
    
    def get_open_orders(self) -> List[VirtualOrder]:
        """
        获取所有未完成订单
        
        Returns:
            未完成订单列表
        """
        return [order for order in self.orders.values() if order.status == "open"]
    
    def match_orders(self, kline: OHLC) -> List[Dict[str, Any]]:
        """
        对单根K线进行订单匹配
        
        规则：
        - 市价单：在Close价格成交
        - 限价单：如果价格在Low-High范围内成交
        - TPSL：检查触发价格
        
        Args:
            kline: K线数据
            
        Returns:
            成交记录列表 [{"order": order, "fill_price": price, "fill_volume": volume}, ...]
        """
        fills = []
        orders_to_remove = []
        
        for txid, order in list(self.orders.items()):
            if order.status != "open":
                continue
            
            # 检查TPSL触发
            if order.parent_txid and order.tpsl_type:
                # 这是TPSL订单
                trigger_price = None
                if order.tpsl_type == "sl":
                    trigger_price = order.stop_loss.get("price") if order.stop_loss else None
                elif order.tpsl_type == "tp":
                    trigger_price = order.take_profit.get("price") if order.take_profit else None
                
                if trigger_price:
                    # 检查是否触发
                    triggered = False
                    if order.type == "buy":  # SL/TP 订单方向与主单相反
                        # 卖单：价格跌破触发价
                        if kline.low <= trigger_price:
                            triggered = True
                    else:
                        # 买单：价格涨破触发价
                        if kline.high >= trigger_price:
                            triggered = True
                    
                    if triggered:
                        # TPSL触发：在触发价成交
                        fill_price = trigger_price
                        fill_volume = order.volume - order.filled
                        fills.append({
                            "order": order,
                            "fill_price": fill_price,
                            "fill_volume": fill_volume,
                            "is_tpsl": True
                        })
                        order.filled = order.volume
                        order.status = "closed"
                        order.closed_at = kline.timestamp
                        orders_to_remove.append(txid)
                        logger.info(f"[MatchingEngine] TPSL order {txid} triggered at {fill_price}")
                        continue
            
            # 普通订单匹配
            if order.ordertype == "market":
                # 市价单：在Close价格成交
                fill_price = kline.close
                fill_volume = order.volume - order.filled
                fills.append({
                    "order": order,
                    "fill_price": fill_price,
                    "fill_volume": fill_volume,
                    "is_tpsl": False
                })
                order.filled = order.volume
                order.status = "closed"
                order.closed_at = kline.timestamp
                orders_to_remove.append(txid)
                logger.info(f"[MatchingEngine] Market order {txid} filled at {fill_price}")
                
            elif order.ordertype == "limit":
                # 限价单：如果价格在Low-High范围内成交
                limit_price = order.price
                if limit_price is None:
                    continue
                
                # 检查是否在价格范围内
                if order.type == "buy":
                    # 买单：如果Low <= limit_price，可以成交
                    if kline.low <= limit_price:
                        fill_price = min(limit_price, kline.high)  # 取限价和最高价的较小值
                        fill_volume = order.volume - order.filled
                        fills.append({
                            "order": order,
                            "fill_price": fill_price,
                            "fill_volume": fill_volume,
                            "is_tpsl": False
                        })
                        order.filled = order.volume
                        order.status = "closed"
                        order.closed_at = kline.timestamp
                        orders_to_remove.append(txid)
                        logger.info(f"[MatchingEngine] Limit buy order {txid} filled at {fill_price}")
                else:
                    # 卖单：如果High >= limit_price，可以成交
                    if kline.high >= limit_price:
                        fill_price = max(limit_price, kline.low)  # 取限价和最低价的较大值
                        fill_volume = order.volume - order.filled
                        fills.append({
                            "order": order,
                            "fill_price": fill_price,
                            "fill_volume": fill_volume,
                            "is_tpsl": False
                        })
                        order.filled = order.volume
                        order.status = "closed"
                        order.closed_at = kline.timestamp
                        orders_to_remove.append(txid)
                        logger.info(f"[MatchingEngine] Limit sell order {txid} filled at {fill_price}")
        
        # 移除已完成的订单
        for txid in orders_to_remove:
            self.orders.pop(txid, None)
        
        return fills
    
    def create_tpsl_orders(self, main_order: VirtualOrder) -> List[VirtualOrder]:
        """
        为主单创建TPSL订单（在主单成交后调用）
        
        Args:
            main_order: 主单
            
        Returns:
            TPSL订单列表
        """
        tpsl_orders = []
        import time
        
        if main_order.stop_loss:
            sl_price = main_order.stop_loss.get("price")
            if sl_price:
                sl_order = VirtualOrder(
                    txid=f"sl_{main_order.txid}_{int(time.time() * 1000)}",
                    pair=main_order.pair,
                    type="sell" if main_order.type == "buy" else "buy",  # 反向
                    ordertype="limit",
                    volume=main_order.volume,
                    status="open",
                    userref=main_order.userref,
                    price=sl_price,
                    created_at=time.time(),
                    parent_txid=main_order.txid,
                    tpsl_type="sl",
                    stop_loss={"price": sl_price}
                )
                tpsl_orders.append(sl_order)
                self.orders[sl_order.txid] = sl_order
        
        if main_order.take_profit:
            tp_price = main_order.take_profit.get("price")
            if tp_price:
                tp_order = VirtualOrder(
                    txid=f"tp_{main_order.txid}_{int(time.time() * 1000)}",
                    pair=main_order.pair,
                    type="sell" if main_order.type == "buy" else "buy",  # 反向
                    ordertype="limit",
                    volume=main_order.volume,
                    status="open",
                    userref=main_order.userref,
                    price=tp_price,
                    created_at=time.time(),
                    parent_txid=main_order.txid,
                    tpsl_type="tp",
                    take_profit={"price": tp_price}
                )
                tpsl_orders.append(tp_order)
                self.orders[tp_order.txid] = tp_order
        
        # OCO逻辑：如果其中一个触发，取消另一个
        if len(tpsl_orders) == 2:
            sl_order, tp_order = tpsl_orders
            # 标记为OCO对（通过userref关联）
            logger.info(f"[MatchingEngine] Created TPSL orders for {main_order.txid}: SL={sl_order.txid}, TP={tp_order.txid}")
        
        return tpsl_orders
    
    def cancel_oco_pair(self, triggered_txid: str) -> None:
        """
        取消OCO对中的另一个订单
        
        Args:
            triggered_txid: 已触发的订单ID
        """
        import time
        triggered_order = self.orders.get(triggered_txid)
        if not triggered_order or not triggered_order.parent_txid:
            return
        
        # 找到同组的另一个TPSL订单
        for txid, order in self.orders.items():
            if (txid != triggered_txid and 
                order.parent_txid == triggered_order.parent_txid and 
                order.status == "open"):
                order.status = "canceled"
                order.canceled_at = time.time()
                order.canceled_reason = "OCO: other side triggered"
                logger.info(f"[MatchingEngine] Canceled OCO pair order {txid} due to {triggered_txid} trigger")

