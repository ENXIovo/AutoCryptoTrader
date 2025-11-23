from __future__ import annotations
from typing import Optional, Literal
from pydantic import BaseModel, Field


class Order(BaseModel):
    """
    Order entity - 订单基本信息
    订单执行由 Hyperliquid 处理
    """
    txid: str = Field(..., description="Transaction ID (unique order identifier)")
    pair: str = Field(..., description="Trading pair, e.g., 'XBTUSDT', 'ETHUSDT'")
    type: Literal["buy", "sell"] = Field(..., description="Order side: buy or sell")
    ordertype: Literal["market", "limit"] = Field(
        ..., description="Order type: market or limit"
    )
    volume: float = Field(..., gt=0, description="Order volume in base asset units")
    filled: float = Field(default=0.0, ge=0, description="Filled volume")
    status: Literal["open", "closed", "canceled"] = Field(
        ..., description="Order status: open, closed, or canceled"
    )
    userref: int = Field(..., description="User reference ID for grouping orders")
    price: Optional[float] = Field(None, gt=0, description="Limit price (None for market orders)")
    created_at: float = Field(..., description="Order creation timestamp")
    
    # TPSL 参数（存储，但不自动创建订单）
    stop_loss: Optional[dict] = Field(None, description="Stop-loss configuration: {'price': float}")
    take_profit: Optional[dict] = Field(None, description="Take-profit configuration: {'price': float}")
    
    # Fill related fields (set when order is filled)
    avg_price: Optional[float] = Field(None, description="Average fill price")
    closed_at: Optional[float] = Field(None, description="Order close timestamp")
    
    # Cancel related fields
    canceled_at: Optional[float] = Field(None, description="Order cancellation timestamp")
    canceled_reason: Optional[str] = Field(None, description="Reason for cancellation")


# Request/Response models for API
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
    oid: int = Field(..., description="Order ID (Hyperliquid oid) to modify")
    coin: str = Field(..., description="Trading pair base asset")
    is_buy: bool = Field(..., description="True for buy, False for sell")
    sz: float = Field(..., gt=0, description="New order size")
    limit_px: float = Field(..., gt=0, description="New limit price")
    order_type: dict = Field(default_factory=lambda: {"limit": {"tif": "Gtc"}}, description="Order type configuration")


class CancelOrderRequest(BaseModel):
    """Request model for canceling an order"""
    coin: str = Field(..., description="Trading pair base asset")
    oid: int = Field(..., description="Order ID (Hyperliquid oid) to cancel")


class UpdateLeverageRequest(BaseModel):
    """Request model for updating leverage"""
    leverage: int = Field(..., ge=1, description="Leverage multiplier (e.g., 21 for 21x)")
    coin: str = Field(..., description="Trading pair base asset (perps only)")
    is_cross: bool = Field(default=True, description="True for cross margin, False for isolated margin")


class UpdateIsolatedMarginRequest(BaseModel):
    """Request model for updating isolated margin"""
    margin: float = Field(..., description="Additional margin amount in USD (can be negative to reduce)")
    coin: str = Field(..., description="Trading pair base asset (perps only)")

