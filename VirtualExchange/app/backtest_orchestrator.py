"""
Backtest Orchestrator - 单职责：回测编排器
整合 Strategy Agent 和回测引擎，在历史时间点上循环执行
统一使用UTC时区
"""
import logging
import asyncio
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
from app.utils.time_utils import ensure_utc
from app.models import VirtualOrder, BacktestReport
from app.backtest_runner import BacktestRunner
from app.config import settings

logger = logging.getLogger(__name__)


class BacktestOrchestrator:
    """
    回测编排器
    - 在历史时间点上循环
    - 每个时间点调用 Strategy Agent
    - 收集订单并用1m K线撮合
    """
    
    def __init__(self, initial_balance: Optional[float] = None):
        """
        初始化回测编排器
        
        Args:
            initial_balance: 初始余额
        """
        self.runner = BacktestRunner(initial_balance)
        self.all_orders: List[VirtualOrder] = []  # 收集所有订单
        logger.info(f"[BacktestOrchestrator] Initialized")
    
    async def run(
        self,
        symbol: str,
        start_time: datetime,
        end_time: datetime,
        meeting_interval: timedelta = timedelta(hours=4),  # 每4小时一次会议
        strategy_agent_url: Optional[str] = None  # Strategy Agent API URL
    ) -> BacktestReport:
        """
        执行完整回测流程
        
        Args:
            symbol: 交易对
            start_time: 开始时间
            end_time: 结束时间
            meeting_interval: 会议间隔（默认4小时）
            strategy_agent_url: Strategy Agent API URL（如果为None，则跳过Agent调用，只撮合已有订单）
            
        Returns:
            回测报告
        """
        start_time = ensure_utc(start_time)
        end_time = ensure_utc(end_time)
        
        logger.info(
            f"[BacktestOrchestrator] Starting orchestrated backtest: "
            f"{symbol} from {start_time} to {end_time}, "
            f"meeting_interval={meeting_interval}"
        )
        
        # 生成会议时间点列表
        meeting_times = self._generate_meeting_times(start_time, end_time, meeting_interval)
        logger.info(f"[BacktestOrchestrator] Generated {len(meeting_times)} meeting time points")
        
        # 在每个时间点执行会议
        for i, meeting_time in enumerate(meeting_times):
            logger.info(f"[BacktestOrchestrator] Meeting {i+1}/{len(meeting_times)} at {meeting_time}")
            
            # 1. 设置回测时间点
            self.runner.set_current_time(meeting_time)
            
            # 1.1. 设置基础价格（用于账户价值计算）
            # 加载该时间点的1m K线，获取当前价格
            from app.data_loader import DataLoader
            data_loader = DataLoader(settings.DATA_STORE_PATH)
            # 获取该时间点之前的最后一根K线（最多往前5分钟）
            lookback_start = meeting_time - timedelta(minutes=5)
            lookback_candles = data_loader.load_candles(
                symbol, 
                lookback_start, 
                meeting_time, 
                "1m"
            )
            if lookback_candles:
                current_price = lookback_candles[-1].close
                self.runner.current_prices[symbol] = current_price
                logger.debug(f"[BacktestOrchestrator] Set current price for {symbol}: ${current_price:.2f}")
            else:
                # 如果没有历史数据，尝试从更早的时间获取
                logger.warning(f"[BacktestOrchestrator] No price data at {meeting_time}, account value may be inaccurate")
            
            # 2. 调用 Strategy Agent（如果提供了URL）
            if strategy_agent_url:
                orders_from_meeting = await self._run_strategy_meeting(
                    meeting_time,
                    strategy_agent_url
                )
                if orders_from_meeting:
                    self.all_orders.extend(orders_from_meeting)
                    logger.info(f"[BacktestOrchestrator] Got {len(orders_from_meeting)} orders from meeting")
            
            # 3. 确定下一个时间点（用于撮合）
            next_meeting_time = meeting_times[i + 1] if i + 1 < len(meeting_times) else end_time
            
            # 4. 用1m K线撮合到下一个时间点
            self._match_orders_until(symbol, meeting_time, next_meeting_time)
        
        # 5. 生成最终报告
        report = self._generate_final_report(symbol, start_time, end_time)
        
        logger.info(
            f"[BacktestOrchestrator] Backtest completed: "
            f"Total orders: {len(self.all_orders)}, "
            f"Total PnL: ${report.total_pnl:.2f}"
        )
        
        return report
    
    def _generate_meeting_times(
        self,
        start_time: datetime,
        end_time: datetime,
        interval: timedelta
    ) -> List[datetime]:
        """
        生成会议时间点列表
        
        Args:
            start_time: 开始时间
            end_time: 结束时间
            interval: 会议间隔
            
        Returns:
            时间点列表
        """
        times = []
        current = start_time
        while current <= end_time:
            times.append(current)
            current += interval
        return times
    
    async def _run_strategy_meeting(
        self,
        meeting_time: datetime,
        strategy_agent_url: str
    ) -> List[VirtualOrder]:
        """
        调用 Strategy Agent 执行会议
        
        Args:
            meeting_time: 会议时间点
            strategy_agent_url: Strategy Agent API URL
            
        Returns:
            订单列表
        """
        try:
            import requests
            import sys
            from pathlib import Path
            
            # 动态导入 Strategy Agent（如果可用）
            # 注意：这需要 Strategy Agent 在 Python path 中
            try:
                sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / "Agents" / "strategy_agent"))
                from app.tool_handlers import set_backtest_timestamp
            except ImportError:
                logger.warning("[BacktestOrchestrator] Cannot import Strategy Agent, skipping meeting")
                return []
            
            # 设置回测时间戳（让工具处理器使用历史数据）
            timestamp = meeting_time.timestamp()
            set_backtest_timestamp(timestamp)
            
            # 调用 Strategy Agent API（回测模式）
            resp = requests.post(
                f"{strategy_agent_url}/analyze",
                json={
                    "backtest_mode": True,
                    "backtest_timestamp": timestamp
                },
                timeout=120  # 回测可能需要更长时间
            )
            resp.raise_for_status()
            result = resp.json()
            
            logger.info(f"[BacktestOrchestrator] Strategy Agent meeting completed at {meeting_time}")
            
            # 从结果中提取订单（需要根据实际API响应格式解析）
            # 这里简化处理，实际需要从CTO的响应中解析订单
            orders = self._extract_orders_from_meeting_result(result, meeting_time)
            
            # 清除回测时间戳
            set_backtest_timestamp(None)
            
            return orders
            
        except Exception as e:
            logger.error(f"[BacktestOrchestrator] Failed to run strategy meeting at {meeting_time}: {e}")
            set_backtest_timestamp(None)
            return []
    
    def _extract_orders_from_meeting_result(
        self,
        result: Dict[str, Any],
        meeting_time: datetime
    ) -> List[VirtualOrder]:
        """
        从会议结果中提取订单
        
        Args:
            result: Strategy Agent 的响应
            meeting_time: 会议时间点
            
        Returns:
            订单列表
        """
        orders = []
        
        # 从 _orders 字段中提取订单（由 agent_runner 提取）
        order_dicts = result.get("_orders", [])
        
        if not order_dicts:
            logger.debug(f"[BacktestOrchestrator] No orders found in meeting result")
            return orders
        
        # 转换为 VirtualOrder
        from app.utils.time_utils import utc_timestamp
        
        for i, order_dict in enumerate(order_dicts):
            try:
                coin = order_dict.get("coin", "")
                if not coin:
                    continue
                
                # 构建pair
                pair = f"{coin}USDT"
                
                # 确定订单类型
                limit_px = float(order_dict.get("limit_px", 0.0))
                ordertype = "market" if limit_px <= 0 else "limit"
                
                # 创建VirtualOrder
                order = VirtualOrder(
                    txid=f"order_{int(meeting_time.timestamp() * 1000)}_{i}",
                    pair=pair,
                    type="buy" if order_dict.get("is_buy") else "sell",
                    ordertype=ordertype,
                    volume=float(order_dict.get("sz", 0.0)),
                    filled=0.0,
                    status="open",
                    userref=int(meeting_time.timestamp() * 1000) % 1000000,
                    price=limit_px if limit_px > 0 else None,
                    created_at=meeting_time.timestamp(),
                    stop_loss=order_dict.get("stop_loss"),
                    take_profit=order_dict.get("take_profit")
                )
                orders.append(order)
                logger.info(f"[BacktestOrchestrator] Extracted order: {order.txid} {order.type} {order.volume} {pair} @ {order.price}")
            except Exception as e:
                logger.warning(f"[BacktestOrchestrator] Failed to create order from {order_dict}: {e}")
                continue
        
        return orders
    
    def _match_orders_until(
        self,
        symbol: str,
        from_time: datetime,
        to_time: datetime
    ) -> None:
        """
        用1m K线撮合订单直到指定时间点
        
        Args:
            symbol: 交易对
            from_time: 开始时间
            to_time: 结束时间
        """
        # 加载1m K线数据
        from app.data_loader import DataLoader
        candles = DataLoader(settings.DATA_STORE_PATH).load_candles(
            symbol, from_time, to_time, "1m"
        )
        
        if not candles:
            logger.warning(f"[BacktestOrchestrator] No 1m candles for matching from {from_time} to {to_time}")
            return
        
        # 添加订单到撮合引擎
        engine = self.runner.get_engine()
        wallet = self.runner.get_wallet()
        
        # 只添加未添加的订单
        existing_txids = {o.txid for o in engine.get_open_orders()}
        for order in self.all_orders:
            if order.txid not in existing_txids and order.status == "open":
                engine.add_order(order)
                current_price = candles[0].close if candles else 0.0
                wallet.place_order(order, current_price)
                existing_txids.add(order.txid)
        
        # 按时间顺序处理每根K线
        for candle in candles:
            # 更新当前价格
            self.runner.current_prices[symbol] = candle.close
            
            # 匹配订单
            fills = engine.match_orders(candle)
            
            # 处理成交
            for fill_info in fills:
                order = fill_info["order"]
                fill_price = fill_info["fill_price"]
                fill_volume = fill_info["fill_volume"]
                
                # 更新订单状态
                if order.filled == 0:
                    order.avg_price = fill_price
                else:
                    total_cost = (order.avg_price or 0) * (order.filled - fill_volume) + fill_price * fill_volume
                    order.avg_price = total_cost / order.filled
                
                # 更新钱包
                trade = wallet.fill_order(
                    order, fill_price, fill_volume,
                    candle=candle,
                    fee_rate=settings.FEE_RATE
                )
                
                # 处理TPSL
                if not fill_info.get("is_tpsl") and order.filled >= order.volume:
                    tpsl_orders = engine.create_tpsl_orders(order)
                
                if fill_info.get("is_tpsl"):
                    engine.cancel_oco_pair(order.txid)
            
            # 更新权益曲线
            current_equity = wallet.get_account_value({symbol: candle.close})
            self.runner.equity_curve.append(current_equity)
        
        logger.debug(f"[BacktestOrchestrator] Matched orders from {from_time} to {to_time}, processed {len(candles)} candles")
    
    def _generate_final_report(
        self,
        symbol: str,
        start_time: datetime,
        end_time: datetime
    ) -> BacktestReport:
        """
        生成最终回测报告
        
        Args:
            symbol: 交易对
            start_time: 开始时间
            end_time: 结束时间
            
        Returns:
            回测报告
        """
        # 使用 BacktestRunner 的报告生成逻辑
        from app.trade_pairer import TradePairer
        from app.portfolio_metrics import PortfolioMetrics
        from app.reproducibility import ReproducibilityInfo
        
        wallet = self.runner.get_wallet()
        orders_dict = {o.txid: o for o in self.all_orders}
        
        # 配对交易
        virtual_trades = wallet.get_trades()
        pairer = TradePairer()
        completed_trades = pairer.pair_trades(virtual_trades, orders_dict)
        
        # 计算组合级指标
        total_time = (end_time - start_time).total_seconds()
        portfolio_metrics = PortfolioMetrics.calculate(
            completed_trades,
            self.runner.equity_curve,
            total_time
        )
        
        # 收集复现信息
        strategy_config = {
            "symbol": symbol,
            "start_time": start_time.isoformat(),
            "end_time": end_time.isoformat(),
            "meeting_count": len(self._generate_meeting_times(start_time, end_time, timedelta(hours=4))),
            "initial_balance": wallet.get_balance()
        }
        reproducibility = ReproducibilityInfo.collect(
            self.runner.used_data_files,
            strategy_config,
            settings.FEE_RATE
        )
        
        # 计算基础指标
        initial_equity = self.runner.equity_curve[0] if self.runner.equity_curve else wallet.get_balance()
        final_equity = self.runner.equity_curve[-1] if self.runner.equity_curve else wallet.get_account_value({symbol: 0.0})
        total_pnl = final_equity - initial_equity
        
        max_equity = max(self.runner.equity_curve) if self.runner.equity_curve else initial_equity
        max_drawdown = min(
            (eq - max_equity) / max_equity if max_equity > 0 else 0.0
            for eq in self.runner.equity_curve
        ) if self.runner.equity_curve else 0.0
        
        return BacktestReport(
            total_pnl=total_pnl,
            win_rate=portfolio_metrics.get("win_rate", 0.0),
            max_drawdown=max_drawdown,
            total_trades=len(completed_trades),
            equity_curve=self.runner.equity_curve,
            trades=[t.model_dump() for t in virtual_trades],
            completed_trades=completed_trades,
            portfolio_metrics=portfolio_metrics,
            reproducibility=reproducibility,
            win_rate_definition="pnl_after_fees > 0",
            breakeven_threshold=1e-6
        )

