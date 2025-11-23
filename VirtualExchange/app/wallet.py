"""
Wallet Management - 单职责：简单钱包管理
单账本余额跟踪，无复杂的冻结/解冻逻辑
统一使用UTC时区
"""
import logging
from typing import Dict, Optional, TYPE_CHECKING
from app.models import VirtualOrder, VirtualPosition, VirtualTrade
from app.utils.time_utils import utc_timestamp

if TYPE_CHECKING:
    from app.models import OHLC

logger = logging.getLogger(__name__)


class Wallet:
    """
    简单钱包管理
    - 单账本余额跟踪
    - 订单扣款/退款
    - 无复杂的冻结/解冻逻辑
    """
    
    def __init__(self, initial_balance: float = 10000.0):
        """
        初始化钱包
        
        Args:
            initial_balance: 初始余额（USD）
        """
        self.balance: float = initial_balance
        self.positions: Dict[str, VirtualPosition] = {}  # pair -> position
        self.trades: list[VirtualTrade] = []
        logger.info(f"[Wallet] Initialized with balance: ${initial_balance:.2f}")
    
    def can_place_order(self, order: VirtualOrder, current_price: float) -> bool:
        """
        检查是否有足够余额下单
        
        Args:
            order: 订单
            current_price: 当前价格
            
        Returns:
            True if can place order, False otherwise
        """
        if order.type == "buy":
            # 买单：需要 USD
            required = order.volume * (order.price or current_price)
            return self.balance >= required
        else:
            # 卖单：需要持仓（简化：假设有足够持仓）
            return True
    
    def place_order(self, order: VirtualOrder, current_price: float) -> bool:
        """
        下单时扣款（立即扣款）
        
        Args:
            order: 订单
            current_price: 当前价格
            
        Returns:
            True if successful, False otherwise
        """
        if not self.can_place_order(order, current_price):
            logger.warning(f"[Wallet] Insufficient balance for order {order.txid}")
            return False
        
        if order.type == "buy":
            # 买单：立即扣款（注意：实际成交时还会扣除手续费）
            cost = order.volume * (order.price or current_price)
            self.balance -= cost
            logger.info(f"[Wallet] Deducted ${cost:.2f} for buy order {order.txid}, balance: ${self.balance:.2f}")
        
        return True
    
    def cancel_order(self, order: VirtualOrder, current_price: float) -> None:
        """
        取消订单时退款（立即退款）
        
        Args:
            order: 订单
            current_price: 当前价格
        """
        if order.status == "open" and order.filled == 0:
            # 完全未成交：全额退款
            if order.type == "buy":
                cost = order.volume * (order.price or current_price)
                self.balance += cost
                logger.info(f"[Wallet] Refunded ${cost:.2f} for canceled buy order {order.txid}, balance: ${self.balance:.2f}")
        elif order.filled > 0:
            # 部分成交：只退未成交部分
            if order.type == "buy":
                unfilled = order.volume - order.filled
                cost = unfilled * (order.price or current_price)
                self.balance += cost
                logger.info(f"[Wallet] Refunded ${cost:.2f} for partially filled canceled buy order {order.txid}, balance: ${self.balance:.2f}")
    
    def fill_order(
        self, 
        order: VirtualOrder, 
        fill_price: float, 
        fill_volume: float,
        candle: Optional["OHLC"] = None,
        fee_rate: float = 0.0
    ) -> VirtualTrade:
        """
        订单成交时更新余额和持仓
        
        Args:
            order: 订单
            fill_price: 成交价格
            fill_volume: 成交数量
            candle: K线数据（用于slippage计算）
            fee_rate: 手续费率
            
        Returns:
            VirtualTrade: 成交记录
        """
        # 计算手续费
        trade_cost = fill_volume * fill_price
        fee = trade_cost * fee_rate
        
        # 计算滑点（A1简化模型）
        slippage = 0.0
        bar_open = None
        bar_close = None
        if candle:
            bar_open = candle.open
            bar_close = candle.close
            if order.ordertype == "market":
                # 市价单：fill_price - bar_close
                slippage = fill_price - bar_close
            # 限价单：slippage = 0（按限价成交）
        
        trade = VirtualTrade(
            txid=f"trade_{int(utc_timestamp() * 1000)}_{len(self.trades)}",
            order_txid=order.txid,
            pair=order.pair,
            type=order.type,
            volume=fill_volume,
            price=fill_price,
            cost=trade_cost,
            timestamp=utc_timestamp(),
            fee=fee,
            slippage=slippage,
            order_type=order.ordertype,
            limit_price=order.price,
            bar_open=bar_open,
            bar_close=bar_close
        )
        
        self.trades.append(trade)
        
        # 更新持仓
        if order.pair not in self.positions:
            self.positions[order.pair] = VirtualPosition(
                pair=order.pair,
                size=0.0,
                avg_entry_price=fill_price,
                last_price=fill_price
            )
        
        position = self.positions[order.pair]
        
        if order.type == "buy":
            # 买单：增加持仓
            old_size = position.size
            old_avg = position.avg_entry_price
            new_size = old_size + fill_volume
            if new_size != 0:
                position.avg_entry_price = (old_size * old_avg + fill_volume * fill_price) / new_size
            position.size = new_size
        else:
            # 卖单：减少持仓（或做空）
            old_size = position.size
            old_avg = position.avg_entry_price
            new_size = old_size - fill_volume
            if new_size != 0:
                position.avg_entry_price = (old_size * old_avg - fill_volume * fill_price) / new_size
            position.size = new_size
            # 卖单成交：增加余额（扣除手续费）
            proceeds = fill_volume * fill_price - fee
            self.balance += proceeds
            logger.info(f"[Wallet] Added ${proceeds:.2f} from sell order {order.txid} (fee: ${fee:.2f}), balance: ${self.balance:.2f}")
        
        position.last_price = fill_price
        position.unrealized_pnl = (fill_price - position.avg_entry_price) * position.size
        
        # 买单：扣除手续费（下单时已扣款，这里再扣手续费）
        if order.type == "buy":
            self.balance -= fee
        
        logger.info(f"[Wallet] Order {order.txid} filled: {fill_volume} @ {fill_price} (fee: ${fee:.2f}, slip: ${slippage:.4f}), position {order.pair}: {position.size:.4f} @ {position.avg_entry_price:.2f}")
        
        return trade
    
    def get_account_value(self, current_prices: Dict[str, float]) -> float:
        """
        计算账户总价值（余额 + 持仓市值）
        
        Args:
            current_prices: 当前价格字典 {pair: price}
            
        Returns:
            账户总价值
        """
        total_value = self.balance
        
        for pair, position in self.positions.items():
            if pair in current_prices:
                current_price = current_prices[pair]
                position_value = position.size * current_price
                total_value += position_value
        
        return total_value
    
    def get_balance(self) -> float:
        """获取当前余额"""
        return self.balance
    
    def get_positions(self) -> Dict[str, VirtualPosition]:
        """获取所有持仓"""
        return self.positions.copy()
    
    def get_trades(self) -> list[VirtualTrade]:
        """获取所有成交记录"""
        return self.trades.copy()

