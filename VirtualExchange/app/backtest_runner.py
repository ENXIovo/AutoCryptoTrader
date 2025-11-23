"""
Backtest Runner - 单职责：回测运行器
加载历史数据，按时间轴加速执行，生成回测报告
统一使用UTC时区
"""
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
from pathlib import Path
from app.utils.time_utils import ensure_utc
from app.models import VirtualOrder, OHLC, BacktestReport
from app.matching_engine import MatchingEngine
from app.wallet import Wallet
from app.data_loader import DataLoader
from app.config import settings
from app.trade_pairer import TradePairer
from app.portfolio_metrics import PortfolioMetrics
from app.reproducibility import ReproducibilityInfo

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
        self.used_data_files: List[Path] = []  # 用于复现信息
        self.current_backtest_time: Optional[datetime] = None  # 当前回测时间点
        logger.info(f"[BacktestRunner] Initialized with balance: ${self.wallet.get_balance():.2f}")
    
    def set_current_time(self, time: datetime) -> None:
        """
        设置当前回测时间点（用于历史数据查询）
        
        Args:
            time: 当前回测时间点（UTC）
        """
        self.current_backtest_time = ensure_utc(time)
        logger.debug(f"[BacktestRunner] Set current backtest time: {self.current_backtest_time}")
    
    def get_current_backtest_time(self) -> Optional[datetime]:
        """获取当前回测时间点"""
        return self.current_backtest_time
    
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
        # 确保时区为UTC
        start_time = ensure_utc(start_time)
        end_time = ensure_utc(end_time)
        
        logger.info(f"[BacktestRunner] Starting backtest: {symbol} {timeframe} from {start_time} to {end_time}")
        
        # 收集策略配置（用于复现信息）
        strategy_config = {
            "symbol": symbol,
            "timeframe": timeframe,
            "start_time": start_time.isoformat(),
            "end_time": end_time.isoformat(),
            "initial_balance": self.wallet.get_balance(),
            "order_count": len(orders)
        }
        
        # 1. 加载历史K线数据（并收集使用的文件）
        candles = self._load_candles_with_files(symbol, start_time, end_time, timeframe)
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
        
        # 2. 添加初始订单到撮合引擎（并收集订单字典用于配对）
        orders_dict: Dict[str, VirtualOrder] = {}  # txid -> order
        for order in orders:
            self.engine.add_order(order)
            orders_dict[order.txid] = order
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
                
                # 更新钱包（传入candle和fee_rate用于计算fee/slippage）
                trade = self.wallet.fill_order(
                    order, 
                    fill_price, 
                    fill_volume,
                    candle=candle,
                    fee_rate=settings.FEE_RATE
                )
                
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
        
        # 4. 生成回测报告（A1完整版）
        final_equity = self.wallet.get_account_value({symbol: candles[-1].close if candles else 0.0})
        total_pnl = final_equity - initial_equity
        
        # 4.1 配对交易
        virtual_trades = self.wallet.get_trades()
        pairer = TradePairer()
        completed_trades = pairer.pair_trades(virtual_trades, orders_dict)
        
        # 4.2 计算组合级指标
        total_time = (end_time - start_time).total_seconds()
        portfolio_metrics = PortfolioMetrics.calculate(
            completed_trades,
            self.equity_curve,
            total_time
        )
        
        # 4.3 收集复现信息
        reproducibility = ReproducibilityInfo.collect(
            self.used_data_files,
            strategy_config,
            settings.FEE_RATE
        )
        
        # 4.4 生成报告
        report = BacktestReport(
            total_pnl=total_pnl,
            win_rate=portfolio_metrics.get("win_rate", 0.0),
            max_drawdown=max_drawdown,
            total_trades=len(completed_trades),
            equity_curve=self.equity_curve,
            trades=[t.model_dump() for t in virtual_trades],  # 保留legacy字段
            completed_trades=completed_trades,
            portfolio_metrics=portfolio_metrics,
            reproducibility=reproducibility,
            win_rate_definition="pnl_after_fees > 0",
            breakeven_threshold=1e-6
        )
        
        logger.info(
            f"[BacktestRunner] Backtest completed: "
            f"PnL=${total_pnl:.2f}, "
            f"WinRate={portfolio_metrics.get('win_rate', 0.0):.2%}, "
            f"MaxDD={max_drawdown:.2%}, "
            f"Trades={len(completed_trades)}, "
            f"ProfitFactor={portfolio_metrics.get('profit_factor', 0.0):.2f}"
        )
        
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
    
    def _load_candles_with_files(
        self,
        symbol: str,
        start_time: datetime,
        end_time: datetime,
        timeframe: str
    ) -> List[OHLC]:
        """
        加载K线数据并收集使用的文件列表
        
        Args:
            symbol: 交易对
            start_time: 开始时间
            end_time: 结束时间
            timeframe: 时间周期
            
        Returns:
            OHLC列表
        """
        # 收集文件列表
        self.used_data_files = []
        base_path = Path(settings.DATA_STORE_PATH)
        candles_path = base_path / "candles"
        
        current_date = start_time.date()
        end_date = end_time.date()
        
        while current_date <= end_date:
            file_path = candles_path / f"{symbol}_{timeframe}" / f"{current_date.strftime('%Y-%m-%d')}.parquet"
            if file_path.exists():
                self.used_data_files.append(file_path)
            current_date += timedelta(days=1)
        
        # 加载数据
        return self.data_loader.load_candles(symbol, start_time, end_time, timeframe)

