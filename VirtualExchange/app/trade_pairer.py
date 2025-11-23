"""
Trade Pairer - 单职责：将VirtualTrade配对成CompletedTrade
FIFO语义，支持多entry/多exit、分批加仓/减仓
统一使用UTC时区
"""
import logging
from typing import List, Dict, Optional, Literal
from collections import defaultdict
from app.models import VirtualTrade, CompletedTrade, VirtualOrder

logger = logging.getLogger(__name__)


class Lot:
    """
    持仓批次（用于FIFO配对）
    """
    def __init__(
        self,
        side: Literal["long", "short"],
        qty: float,
        price: float,
        time: float,
        fee: float,
        fills: List[VirtualTrade]
    ):
        self.side = side
        self.qty = qty
        self.price = price
        self.time = time
        self.fee = fee
        self.fills = fills.copy()
        self.initial_sl_price: Optional[float] = None  # 从主单获取


class TradePairer:
    """
    交易配对器 - FIFO语义
    支持分批加仓/减仓/部分平仓
    """
    
    def __init__(self):
        """初始化配对器"""
        logger.info("[TradePairer] Initialized")
    
    def pair_trades(
        self,
        virtual_trades: List[VirtualTrade],
        orders: Dict[str, VirtualOrder]  # txid -> order（用于获取initial_sl_price）
    ) -> List[CompletedTrade]:
        """
        将VirtualTrade配对成CompletedTrade
        
        逻辑：
        - 按时间排序
        - FIFO：先开的仓先平
        - 支持多entry/多exit
        - 支持部分平仓
        
        Args:
            virtual_trades: 所有成交记录
            orders: 订单字典（用于获取initial_sl_price）
            
        Returns:
            完整交易列表
        """
        if not virtual_trades:
            return []
        
        # 按pair分组
        trades_by_pair = defaultdict(list)
        for trade in sorted(virtual_trades, key=lambda t: t.timestamp):
            trades_by_pair[trade.pair].append(trade)
        
        completed_trades = []
        
        for pair, trades in trades_by_pair.items():
            # 当前持仓方向（long/short/flat）
            current_side: Optional[Literal["long", "short"]] = None
            open_lots: List[Lot] = []  # FIFO队列
            
            for trade in trades:
                # 判断是开仓还是平仓
                is_opening = self._is_opening_position(trade, current_side, open_lots)
                
                if is_opening:
                    # 开仓：加入open_lots
                    side = "long" if trade.type == "buy" else "short"
                    lot = Lot(
                        side=side,
                        qty=trade.volume,
                        price=trade.price,
                        time=trade.timestamp,
                        fee=trade.fee,
                        fills=[trade]
                    )
                    
                    # 从订单获取initial_sl_price
                    order = orders.get(trade.order_txid)
                    if order and order.stop_loss:
                        lot.initial_sl_price = order.stop_loss.get("price")
                    
                    open_lots.append(lot)
                    current_side = side
                    logger.debug(f"[TradePairer] Opened {side} lot: {trade.volume} @ {trade.price}")
                    
                else:
                    # 平仓：从open_lots中FIFO配对
                    qty_to_close = trade.volume
                    current_completed: Optional[CompletedTrade] = None
                    
                    while qty_to_close > 0 and open_lots:
                        lot = open_lots[0]
                        
                        # 检查方向是否匹配
                        if (lot.side == "long" and trade.type == "sell") or \
                           (lot.side == "short" and trade.type == "buy"):
                            # 方向匹配：配对
                            close_qty = min(lot.qty, qty_to_close)
                            
                            # 创建或更新CompletedTrade
                            if current_completed is None:
                                # 创建新的CompletedTrade
                                current_completed = CompletedTrade(
                                    pair=pair,
                                    side=lot.side,
                                    entry_fills=lot.fills.copy(),
                                    exit_fills=[trade],
                                    entry_time=lot.time,
                                    exit_time=trade.timestamp,
                                    qty=close_qty,
                                    avg_entry_price=lot.price,
                                    avg_exit_price=trade.price,
                                    fees=lot.fee + trade.fee,
                                    slippage=sum(f.slippage for f in lot.fills) + trade.slippage,
                                    pnl_before_fees=0.0,  # 稍后计算
                                    pnl=0.0,  # 稍后计算
                                    duration=trade.timestamp - lot.time,
                                    initial_sl_price=lot.initial_sl_price
                                )
                            else:
                                # 追加到现有CompletedTrade（多entry/多exit）
                                current_completed.entry_fills.extend(lot.fills)
                                current_completed.exit_fills.append(trade)
                                # 重新计算平均价格
                                total_entry_cost = sum(f.cost for f in current_completed.entry_fills)
                                total_entry_qty = sum(f.volume for f in current_completed.entry_fills)
                                current_completed.avg_entry_price = total_entry_cost / total_entry_qty if total_entry_qty > 0 else 0.0
                                current_completed.avg_exit_price = trade.price  # 简化：使用最新exit价格
                                current_completed.fees += trade.fee
                                current_completed.slippage += trade.slippage
                                current_completed.exit_time = trade.timestamp
                                current_completed.duration = current_completed.exit_time - current_completed.entry_time
                            
                            # 更新lot
                            lot.qty -= close_qty
                            qty_to_close -= close_qty
                            
                            # 如果lot完全平完，移除
                            if lot.qty <= 1e-8:  # 浮点误差
                                open_lots.pop(0)
                            else:
                                # 部分平仓：需要拆分lot（简化：调整qty和price）
                                # 实际应该创建新lot，但为简化，我们调整当前lot
                                pass
                        
                        else:
                            # 方向不匹配：这是反向开仓（反手）
                            # 先平掉当前持仓，再开新仓
                            if open_lots:
                                # 平掉所有当前持仓
                                lot = open_lots.pop(0)
                                if current_completed is None:
                                    current_completed = CompletedTrade(
                                        pair=pair,
                                        side=lot.side,
                                        entry_fills=lot.fills.copy(),
                                        exit_fills=[trade],
                                        entry_time=lot.time,
                                        exit_time=trade.timestamp,
                                        qty=lot.qty,
                                        avg_entry_price=lot.price,
                                        avg_exit_price=trade.price,
                                        fees=lot.fee + trade.fee,
                                        slippage=sum(f.slippage for f in lot.fills) + trade.slippage,
                                        pnl_before_fees=0.0,
                                        pnl=0.0,
                                        duration=trade.timestamp - lot.time,
                                        initial_sl_price=lot.initial_sl_price
                                    )
                                qty_to_close -= lot.qty
                            
                            # 开新仓
                            new_side = "long" if trade.type == "buy" else "short"
                            new_lot = Lot(
                                side=new_side,
                                qty=qty_to_close,
                                price=trade.price,
                                time=trade.timestamp,
                                fee=trade.fee,
                                fills=[trade]
                            )
                            order = orders.get(trade.order_txid)
                            if order and order.stop_loss:
                                new_lot.initial_sl_price = order.stop_loss.get("price")
                            open_lots.append(new_lot)
                            current_side = new_side
                            qty_to_close = 0
                            break
                    
                    # 如果还有未平完的，说明是反向开仓
                    if qty_to_close > 0:
                        new_side = "long" if trade.type == "buy" else "short"
                        new_lot = Lot(
                            side=new_side,
                            qty=qty_to_close,
                            price=trade.price,
                            time=trade.timestamp,
                            fee=trade.fee,
                            fills=[trade]
                        )
                        order = orders.get(trade.order_txid)
                        if order and order.stop_loss:
                            new_lot.initial_sl_price = order.stop_loss.get("price")
                        open_lots.append(new_lot)
                        current_side = new_side
                    
                    # 完成当前CompletedTrade的计算
                    if current_completed:
                        current_completed = self._calculate_trade_metrics(current_completed)
                        completed_trades.append(current_completed)
                        logger.debug(f"[TradePairer] Completed {current_completed.side} trade: qty={current_completed.qty:.4f}, pnl=${current_completed.pnl:.2f}")
        
        logger.info(f"[TradePairer] Paired {len(virtual_trades)} fills into {len(completed_trades)} completed trades")
        return completed_trades
    
    def _is_opening_position(
        self,
        trade: VirtualTrade,
        current_side: Optional[Literal["long", "short"]],
        open_lots: List[Lot]
    ) -> bool:
        """
        判断是否是开仓
        
        逻辑：
        - 如果当前无持仓（flat），则是开仓
        - 如果当前持仓方向与trade方向一致，则是加仓
        - 如果当前持仓方向与trade方向相反，则是平仓或反手
        """
        trade_side = "long" if trade.type == "buy" else "short"
        
        if current_side is None:
            # 无持仓：开仓
            return True
        
        if current_side == trade_side:
            # 同方向：加仓
            return True
        
        # 反方向：平仓或反手（需要看open_lots的qty）
        if open_lots:
            total_open_qty = sum(lot.qty for lot in open_lots)
            if total_open_qty >= trade.volume:
                # 有足够持仓：平仓
                return False
            else:
                # 持仓不足：先平仓再开仓（反手）
                return False
        
        return False
    
    def _calculate_trade_metrics(self, trade: CompletedTrade) -> CompletedTrade:
        """
        计算交易的PnL和R-multiple
        """
        # 计算平均entry/exit价格（加权）
        total_entry_cost = sum(f.cost for f in trade.entry_fills)
        total_entry_qty = sum(f.volume for f in trade.entry_fills)
        trade.avg_entry_price = total_entry_cost / total_entry_qty if total_entry_qty > 0 else 0.0
        
        total_exit_cost = sum(f.cost for f in trade.exit_fills)
        total_exit_qty = sum(f.volume for f in trade.exit_fills)
        trade.avg_exit_price = total_exit_cost / total_exit_qty if total_exit_qty > 0 else 0.0
        
        # 计算总费用和滑点
        trade.fees = sum(f.fee for f in trade.entry_fills) + sum(f.fee for f in trade.exit_fills)
        trade.slippage = sum(f.slippage for f in trade.entry_fills) + sum(f.slippage for f in trade.exit_fills)
        
        # 计算PnL
        if trade.side == "long":
            trade.pnl_before_fees = (trade.avg_exit_price - trade.avg_entry_price) * trade.qty
        else:  # short
            trade.pnl_before_fees = (trade.avg_entry_price - trade.avg_exit_price) * trade.qty
        
        trade.pnl = trade.pnl_before_fees - trade.fees
        
        # 计算R-multiple（如果有initial_sl_price）
        if trade.initial_sl_price:
            if trade.side == "long":
                risk = abs(trade.avg_entry_price - trade.initial_sl_price) * trade.qty
            else:  # short
                risk = abs(trade.initial_sl_price - trade.avg_entry_price) * trade.qty
            
            if risk > 0:
                trade.r_multiple = trade.pnl / risk
            else:
                trade.r_multiple = None
        else:
            trade.r_multiple = None
        
        return trade

