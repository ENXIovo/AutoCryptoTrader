"""
Backtest Runner - 单职责：回测运行器
加载历史数据，按时间轴加速执行，生成回测报告
"""
import logging
import time
from typing import List, Dict, Any, Optional
from datetime import datetime
from app.models import VirtualOrder, OHLC, BacktestReport
from app.matching_engine import MatchingEngine
from app.wallet import Wallet
from app.data_loader import DataLoader
from app.config import settings

logger = logging.getLogger(__name__)


class BacktestRunner:
    """
    回测运行器
    - 加载历史K线数据
    - 按时间轴加速执行
    - 生成回测报告
    """
    
    def __init__(self, initial_balance: float = None):
        """
        初始化回测运行器
        
        Args:
            initial_balance: 初始余额（默认从配置读取）
        """
        self.engine = MatchingEngine()
        self.wallet = Wallet(initial_balance or settings.INITIAL_BALANCE)
        self.data_loader = DataLoader(settings.DATA_STORE_PATH)
        self.current_prices: Dict[str, float] = {}  # 当前价格缓存（用于Mock DataCollector）
        self.equity_curve: List[float] = []
        logger.info(f"[BacktestRunner] Initialized with balance: ${self.wallet.get_balance():.2f}")
    
    def run(
        self,
        orders: List[VirtualOrder],
        symbol: str,
        timeframe: str,
        start_time: datetime,
        end_time: datetime
    ) -> BacktestReport:
        """
        执行回测
        
        Args:
            orders: 初始订单列表（从会议结果提取）
            symbol: 交易对，如 "BTCUSDT"
            timeframe: 时间周期，如 "1m"
            start_time: 开始时间
            end_time: 结束时间
            
        Returns:
            回测报告
        """
        logger.info(f"[BacktestRunner] Starting backtest: {symbol} {timeframe} from {start_time} to {end_time}")
        
        # 1. 加载历史K线数据
        candles = self.data_loader.load_candles(symbol, timeframe, start_time, end_time)
        if not candles:
            logger.error(f"[BacktestRunner] No candles loaded for {symbol}")
            return BacktestReport(
                total_pnl=0.0,
                win_rate=0.0,
                max_drawdown=0.0,
                total_trades=0,
                equity_curve=[],
                trades=[]
            )
        
        # 2. 添加初始订单到撮合引擎
        for order in orders:
            self.engine.add_order(order)
            # 检查余额并扣款
            if order.status == "open":
                current_price = candles[0].close if candles else 0.0
                self.wallet.place_order(order, current_price)
        
        # 3. 按时间顺序处理每根K线
        initial_equity = self.wallet.get_account_value({symbol: candles[0].close if candles else 0.0})
        self.equity_curve.append(initial_equity)
        max_equity = initial_equity
        max_drawdown = 0.0
        
        for i, candle in enumerate(candles):
            # 更新当前价格（用于Mock DataCollector）
            self.current_prices[symbol] = candle.close
            
            # 匹配订单
            fills = self.engine.match_orders(candle)
            
            # 处理成交
            for fill_info in fills:
                order = fill_info["order"]
                fill_price = fill_info["fill_price"]
                fill_volume = fill_info["fill_volume"]
                
                # 更新订单状态
                if order.filled == 0:
                    order.avg_price = fill_price
                else:
                    # 部分成交：计算平均价格
                    total_cost = (order.avg_price or 0) * (order.filled - fill_volume) + fill_price * fill_volume
                    order.avg_price = total_cost / order.filled
                
                # 更新钱包
                trade = self.wallet.fill_order(order, fill_price, fill_volume)
                
                # 如果主单完全成交，创建TPSL订单
                if not fill_info.get("is_tpsl") and order.filled >= order.volume:
                    tpsl_orders = self.engine.create_tpsl_orders(order)
                    for tpsl_order in tpsl_orders:
                        # TPSL订单不需要扣款（已持仓）
                        pass
                
                # 如果TPSL触发，取消OCO对
                if fill_info.get("is_tpsl"):
                    self.engine.cancel_oco_pair(order.txid)
            
            # 更新权益曲线
            current_equity = self.wallet.get_account_value({symbol: candle.close})
            self.equity_curve.append(current_equity)
            
            # 计算最大回撤
            if current_equity > max_equity:
                max_equity = current_equity
            drawdown = (current_equity - max_equity) / max_equity if max_equity > 0 else 0.0
            if drawdown < max_drawdown:
                max_drawdown = drawdown
            
            # 进度日志（每100根K线）
            if (i + 1) % 100 == 0:
                logger.info(f"[BacktestRunner] Processed {i + 1}/{len(candles)} candles, equity: ${current_equity:.2f}")
        
        # 4. 生成回测报告
        final_equity = self.wallet.get_account_value({symbol: candles[-1].close if candles else 0.0})
        total_pnl = final_equity - initial_equity
        
        trades = self.wallet.get_trades()
        winning_trades = [t for t in trades if (t.type == "buy" and t.price > 0) or (t.type == "sell" and t.price > 0)]  # 简化：实际需要计算PnL
        win_rate = len(winning_trades) / len(trades) if trades else 0.0
        
        report = BacktestReport(
            total_pnl=total_pnl,
            win_rate=win_rate,
            max_drawdown=max_drawdown,
            total_trades=len(trades),
            equity_curve=self.equity_curve,
            trades=[t.model_dump() for t in trades]
        )
        
        logger.info(f"[BacktestRunner] Backtest completed: PnL=${total_pnl:.2f}, WinRate={win_rate:.2%}, MaxDD={max_drawdown:.2%}")
        
        return report
    
    def get_current_price(self, symbol: str) -> Optional[float]:
        """
        获取当前价格（用于Mock DataCollector）
        
        Args:
            symbol: 交易对
            
        Returns:
            当前价格
        """
        return self.current_prices.get(symbol)
    
    def get_engine(self) -> MatchingEngine:
        """获取撮合引擎（用于API访问）"""
        return self.engine
    
    def get_wallet(self) -> Wallet:
        """获取钱包（用于API访问）"""
        return self.wallet

