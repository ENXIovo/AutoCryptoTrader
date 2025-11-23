"""
Portfolio Metrics - 单职责：计算组合级指标
基于CompletedTrade和equity_curve
统一使用UTC时区
"""
import logging
from typing import List, Dict, Any
from app.models import CompletedTrade

logger = logging.getLogger(__name__)


class PortfolioMetrics:
    """
    组合级指标计算器
    """
    
    @staticmethod
    def calculate(
        completed_trades: List[CompletedTrade],
        equity_curve: List[float],
        total_time: float  # seconds
    ) -> Dict[str, Any]:
        """
        计算所有组合级指标
        
        Args:
            completed_trades: 完整交易列表
            equity_curve: 权益曲线
            total_time: 总时间（秒）
            
        Returns:
            组合级指标字典
        """
        if not completed_trades:
            return PortfolioMetrics._empty_metrics()
        
        # Win/Loss/Breakeven分类（按pnl_after_fees）
        breakeven_threshold = 1e-6
        wins = [t for t in completed_trades if t.pnl > breakeven_threshold]
        losses = [t for t in completed_trades if t.pnl < -breakeven_threshold]
        breakevens = [t for t in completed_trades if -breakeven_threshold <= t.pnl <= breakeven_threshold]
        
        # Win rate（只算wins和losses，breakeven不参与）
        total_decided = len(wins) + len(losses)
        win_rate = len(wins) / total_decided if total_decided > 0 else 0.0
        
        # Avg win/loss
        avg_win = sum(t.pnl for t in wins) / len(wins) if wins else 0.0
        avg_loss = sum(t.pnl for t in losses) / len(losses) if losses else 0.0
        
        # Profit factor
        total_profit = sum(t.pnl for t in wins)
        total_loss = abs(sum(t.pnl for t in losses))
        profit_factor = total_profit / total_loss if total_loss > 0 else 0.0
        
        # Exposure（时间占用）
        total_exposure_time = sum(t.duration for t in completed_trades)
        exposure = total_exposure_time / total_time if total_time > 0 else 0.0
        
        # Turnover（换手率）
        total_volume = sum(t.qty * t.avg_entry_price for t in completed_trades)
        avg_equity = sum(equity_curve) / len(equity_curve) if equity_curve else 0.0
        turnover = total_volume / avg_equity if avg_equity > 0 else 0.0
        
        # MDD duration（从equity_curve计算）
        mdd_duration = PortfolioMetrics._calculate_mdd_duration(equity_curve)
        
        # R-multiple统计（只统计有r_multiple的交易）
        trades_with_r = [t for t in completed_trades if t.r_multiple is not None]
        avg_r_multiple = sum(t.r_multiple for t in trades_with_r) / len(trades_with_r) if trades_with_r else None
        
        return {
            "win_rate": win_rate,
            "avg_win": avg_win,
            "avg_loss": avg_loss,
            "profit_factor": profit_factor,
            "exposure": exposure,
            "turnover": turnover,
            "mdd_duration": mdd_duration,  # bars
            "win_count": len(wins),
            "loss_count": len(losses),
            "breakeven_count": len(breakevens),
            "avg_r_multiple": avg_r_multiple,
            "trades_with_r": len(trades_with_r)
        }
    
    @staticmethod
    def _calculate_mdd_duration(equity_curve: List[float]) -> float:
        """
        计算最大回撤持续时间（bars）
        
        Args:
            equity_curve: 权益曲线
            
        Returns:
            最大回撤持续时间（bars）
        """
        if len(equity_curve) < 2:
            return 0.0
        
        max_equity = equity_curve[0]
        mdd_start = 0
        mdd_duration = 0.0
        current_dd_duration = 0.0
        
        for i, equity in enumerate(equity_curve):
            if equity > max_equity:
                max_equity = equity
                mdd_start = i
                current_dd_duration = 0.0
            else:
                current_dd_duration = i - mdd_start
                if current_dd_duration > mdd_duration:
                    mdd_duration = current_dd_duration
        
        return mdd_duration
    
    @staticmethod
    def _empty_metrics() -> Dict[str, Any]:
        """返回空指标"""
        return {
            "win_rate": 0.0,
            "avg_win": 0.0,
            "avg_loss": 0.0,
            "profit_factor": 0.0,
            "exposure": 0.0,
            "turnover": 0.0,
            "mdd_duration": 0.0,
            "win_count": 0,
            "loss_count": 0,
            "breakeven_count": 0,
            "avg_r_multiple": None,
            "trades_with_r": 0
        }

