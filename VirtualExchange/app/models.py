"""
Data Models - 单职责：定义回测系统的数据模型
"""
from __future__ import annotations
from typing import Optional, Literal, List, Dict, Any
from pydantic import BaseModel, Field
from datetime import datetime


# ========== 核心实体 ==========

class VirtualOrder(BaseModel):
    """
    虚拟订单实体 - 回测系统订单
    """
    txid: str = Field(..., description="Transaction ID (unique order identifier)")
    pair: str = Field(..., description="Trading pair, e.g., 'BTCUSDT', 'ETHUSDT'")
    type: Literal["buy", "sell"] = Field(..., description="Order side: buy or sell")
    ordertype: Literal["market", "limit"] = Field(
        ..., description="Order type: market or limit"
    )
    volume: float = Field(..., gt=0, description="Order volume in base asset units")
    filled: float = Field(default=0.0, ge=0, description="Filled volume")
    status: Literal["open", "closed", "canceled", "pending"] = Field(
        ..., description="Order status"
    )
    userref: int = Field(..., description="User reference ID for grouping orders")
    price: Optional[float] = Field(None, gt=0, description="Limit price (None for market orders)")
    created_at: float = Field(..., description="Order creation timestamp")
    
    # TPSL 参数
    stop_loss: Optional[dict] = Field(None, description="Stop-loss configuration: {'price': float}")
    take_profit: Optional[dict] = Field(None, description="Take-profit configuration: {'price': float}")
    
    # Fill related fields
    avg_price: Optional[float] = Field(None, description="Average fill price")
    closed_at: Optional[float] = Field(None, description="Order close timestamp")
    
    # Cancel related fields
    canceled_at: Optional[float] = Field(None, description="Order cancellation timestamp")
    canceled_reason: Optional[str] = Field(None, description="Reason for cancellation")
    
    # TPSL 关联
    parent_txid: Optional[str] = Field(None, description="Parent order txid (for TPSL orders)")
    tpsl_type: Optional[Literal["sl", "tp"]] = Field(None, description="TPSL type (for TPSL orders)")


class VirtualPosition(BaseModel):
    """
    虚拟持仓实体
    """
    pair: str = Field(..., description="Trading pair")
    size: float = Field(..., description="Position size (positive = long, negative = short)")
    avg_entry_price: float = Field(..., gt=0, description="Average entry price")
    unrealized_pnl: float = Field(default=0.0, description="Unrealized PnL")
    last_price: float = Field(..., gt=0, description="Last price for PnL calculation")


class VirtualTrade(BaseModel):
    """
    虚拟成交记录 - 扩展版（支持配对和指标计算）
    """
    txid: str = Field(..., description="Trade ID")
    order_txid: str = Field(..., description="Order txid")
    pair: str = Field(..., description="Trading pair")
    type: Literal["buy", "sell"] = Field(..., description="Trade side")
    volume: float = Field(..., gt=0, description="Trade volume")
    price: float = Field(..., gt=0, description="Trade price")
    cost: float = Field(..., gt=0, description="Trade cost (volume * price)")
    timestamp: float = Field(..., description="Trade timestamp")
    
    # 新增字段（A1：支持配对和指标计算）
    fee: float = Field(default=0.0, ge=0, description="Trading fee for this fill")
    slippage: float = Field(default=0.0, description="Slippage (market orders only)")
    order_type: Literal["market", "limit"] = Field(..., description="Order type")
    limit_price: Optional[float] = Field(None, description="Limit price (if limit order)")
    bar_open: Optional[float] = Field(None, description="Bar open price at fill time")
    bar_close: Optional[float] = Field(None, description="Bar close price at fill time")


# ========== API 请求/响应模型 ==========

class PlaceOrderRequest(BaseModel):
    """Request model for placing an order"""
    coin: str = Field(..., description="Base asset, e.g., 'BTC', 'ETH', 'XBT'")
    is_buy: bool = Field(..., description="True for buy, False for sell")
    sz: float = Field(..., gt=0, description="Order size in base asset units")
    limit_px: float = Field(..., ge=0, description="Limit price (0 for market orders)")
    order_type: dict = Field(default_factory=lambda: {"limit": {"tif": "Gtc"}}, description="Order type configuration")
    reduce_only: bool = Field(default=False, description="If true, order can only reduce position")
    stop_loss: dict = Field(..., description="Stop-loss configuration: {'price': float}")
    take_profit: dict = Field(..., description="Take-profit configuration: {'price': float}")


class ModifyOrderRequest(BaseModel):
    """Request model for modifying an order - all fields required"""
    oid: int = Field(..., description="Order ID to modify")
    coin: str = Field(..., description="Trading pair base asset")
    is_buy: bool = Field(..., description="True for buy, False for sell")
    sz: float = Field(..., gt=0, description="New order size")
    limit_px: float = Field(..., gt=0, description="New limit price")
    order_type: dict = Field(default_factory=lambda: {"limit": {"tif": "Gtc"}}, description="Order type configuration")


class CancelOrderRequest(BaseModel):
    """Request model for canceling an order"""
    coin: str = Field(..., description="Trading pair base asset")
    oid: int = Field(..., description="Order ID to cancel")


# ========== K线数据模型 ==========

class OHLC(BaseModel):
    """
    OHLC 数据模型（用于撮合引擎）
    """
    timestamp: float = Field(..., description="K线时间戳")
    open: float = Field(..., gt=0, description="开盘价")
    high: float = Field(..., gt=0, description="最高价")
    low: float = Field(..., gt=0, description="最低价")
    close: float = Field(..., gt=0, description="收盘价")
    volume: float = Field(default=0.0, ge=0, description="成交量")


# ========== 完整交易模型（A1） ==========

class CompletedTrade(BaseModel):
    """
    完整交易 - 支持多entry/多exit
    表示一段持仓生命周期
    """
    pair: str = Field(..., description="Trading pair")
    side: Literal["long", "short"] = Field(..., description="Position side")
    
    # 多笔fills
    entry_fills: List["VirtualTrade"] = Field(default_factory=list, description="Entry fills")
    exit_fills: List["VirtualTrade"] = Field(default_factory=list, description="Exit fills")
    
    # 聚合指标
    entry_time: float = Field(..., description="First entry fill timestamp")
    exit_time: float = Field(..., description="Last exit fill timestamp")
    qty: float = Field(..., gt=0, description="Total quantity (absolute)")
    
    # 平均价格
    avg_entry_price: float = Field(..., gt=0, description="Weighted average entry price")
    avg_exit_price: float = Field(..., gt=0, description="Weighted average exit price")
    
    # 费用和滑点
    fees: float = Field(default=0.0, ge=0, description="Total fees (entry + exit)")
    slippage: float = Field(default=0.0, description="Total slippage (entry + exit)")
    
    # 盈亏
    pnl: float = Field(..., description="PnL after fees")
    pnl_before_fees: float = Field(..., description="PnL before fees")
    
    # 持续时间
    duration: float = Field(..., ge=0, description="Duration in seconds")
    
    # R-multiple（可空）
    r_multiple: Optional[float] = Field(None, description="R-multiple (if initial_sl_price provided)")
    initial_sl_price: Optional[float] = Field(None, description="Initial stop-loss price")


# ========== 回测报告模型 ==========

class BacktestReport(BaseModel):
    """
    回测报告 - A1完整版
    """
    # 基础指标（保留向后兼容）
    total_pnl: float = Field(..., description="Total PnL")
    win_rate: float = Field(..., ge=0, le=1, description="Win rate (0-1)")
    max_drawdown: float = Field(..., description="Maximum drawdown")
    total_trades: int = Field(..., ge=0, description="Total number of trades")
    equity_curve: List[float] = Field(..., description="Equity curve over time")
    trades: List[Dict[str, Any]] = Field(default_factory=list, description="List of all trades (legacy)")
    
    # 新增：交易级数据
    completed_trades: List[CompletedTrade] = Field(default_factory=list, description="Completed trades with full metrics")
    
    # 新增：组合级指标
    portfolio_metrics: Dict[str, Any] = Field(default_factory=dict, description="Portfolio-level metrics")
    
    # 新增：复现信息
    reproducibility: Dict[str, Any] = Field(default_factory=dict, description="Reproducibility metadata")
    
    # 元数据（定义说明）
    win_rate_definition: str = Field(default="pnl_after_fees > 0", description="Win rate calculation definition")
    breakeven_threshold: float = Field(default=1e-6, description="Breakeven threshold")
