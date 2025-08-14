from enum import Enum
from typing import List, Optional, Union

from pydantic import BaseModel, Field, field_serializer, model_validator, ConfigDict


# -------- 公共枚举 --------
class OrderType(str, Enum):
    market = "market"
    limit = "limit"
    iceberg = "iceberg"
    stop_loss = "stop-loss"
    take_profit = "take-profit"
    stop_loss_limit = "stop-loss-limit"
    take_profit_limit = "take-profit-limit"
    trailing_stop = "trailing-stop"
    trailing_stop_limit = "trailing-stop-limit"
    settle_position = "settle-position"


class OrderSide(str, Enum):
    buy = "buy"
    sell = "sell"


class TriggerType(str, Enum):
    index = "index"
    last = "last"


class TimeInForce(str, Enum):
    GTC = "GTC"
    IOC = "IOC"
    GTD = "GTD"


class SelfTradePrevention(str, Enum):
    cancel_newest = "cancel-newest"
    cancel_oldest = "cancel-oldest"
    cancel_both = "cancel-both"


# -------- Add Order --------
class CloseOrder(BaseModel):
    ordertype: OrderType
    price: Optional[str] = None
    price2: Optional[str] = None


class AddOrderRequest(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)

    # ─────── metadata ───────
    nonce: Optional[int] = None
    userref: Optional[int] = None


    # ─────── main params ───────
    pair: str = Field(..., example="XBTUSD", pattern=r"^[A-Z]{4,}$")
    type: OrderSide = Field(..., example="buy")
    ordertype: OrderType = Field(..., example="limit")
    volume: str = Field(..., example="1.25")

    # ─────── price / risk ───────
    price: Optional[str] = None
    price2: Optional[str] = None
    displayvol: Optional[str] = None
    leverage: Optional[str] = None
    trigger: Optional[TriggerType] = None
    reduce_only: Optional[bool] = None
    stptype: Optional[SelfTradePrevention] = None
    oflags: Optional[Union[str, List[str]]] = None
    timeinforce: Optional[TimeInForce] = None
    starttm: Optional[str] = None
    expiretm: Optional[str] = None
    deadline: Optional[str] = None
    validate_only: Optional[bool] = Field(None, alias="validate")

    # ─────── conditional close ───────
    close_ordertype: Optional[OrderType] = Field(
        None, alias="close[ordertype]", description="条件单类型"
    )
    close_price: Optional[str] = Field(
        None, alias="close[price]", description="条件单价格或偏移量"
    )
    close_price2: Optional[str] = Field(
        None, alias="close[price2]", description="备用价格（如止损限价）"
    )

    # oflags 可以传列表，序列化时转成逗号串
    @field_serializer("oflags", when_used="json")
    def _serialise_oflags(self, v):
        if v is None:
            return None
        return ",".join(v) if isinstance(v, list) else v


# -------- Amend Order --------
class AmendOrderRequest(BaseModel):
    """
    字段完全对齐 Kraken AmendOrder 文档。
    """
    nonce: Optional[int] = None
    txid: Optional[str] = None

    order_qty: Optional[str] = None          # 新数量
    display_qty: Optional[str] = None        # 冰山可见量
    limit_price: Optional[str] = None        # 新限价
    trigger_price: Optional[str] = None      # 新触发价
    post_only: Optional[bool] = None
    deadline: Optional[str] = None


# -------- Cancel Order --------
class CancelOrderRequest(BaseModel):
    nonce: Optional[int] = None
    txid: Union[None, str, int] = None       # Kraken 文档允许 str 或 int
    userref: Optional[int] = None            # 支持批量按 userref 撤单

class TradeStatus(str, Enum):
    PENDING = "PENDING"              # 计划已创建，等待执行
    ACTIVE = "ACTIVE"                # 初始订单成交，止损已挂，正在监控TP
    TP1_HIT = "TP1_HIT"              # 已触发第一止盈，剩余部分仍在监控
    CLOSING = "CLOSING"              # 正在平仓
    CLOSED = "CLOSED"                # 已完成

class TakeProfitTarget(BaseModel):
    price: float
    percentage_to_sell: float = Field(..., gt=0, le=100, description="卖出仓位的百分比 (1-100)")
    is_hit: bool = False

class TradePlan(BaseModel):
    """
    定义一个完整的交易计划，将作为Celery任务的输入
    """
    symbol: str
    side: OrderSide
    entry_price: float
    position_size: float
    stop_loss_price: float
    take_profits: List[TakeProfitTarget] # 支持多级止盈

    # 元数据/分组
    userref: Optional[int] = Field(None, description="分组标识（优先使用）")

    # 入场细节（对齐 AddOrder，精简到必要字段）
    entry_ordertype: OrderType = OrderType.market
    entry_price2: Optional[float] = None
    oflags: Optional[Union[str, List[str]]] = None
    timeinforce: Optional[TimeInForce] = None
    trigger: Optional[TriggerType] = None

class TradeLedgerEntry(TradePlan):
    """
    储存在 Redis 的交易台账条目。按 trade_id 唯一标识，支持同一 symbol 多笔并行。
    """
    trade_id: str
    status: TradeStatus = TradeStatus.PENDING
    entry_txid: Optional[str] = None
    stop_loss_txid: Optional[str] = None
    remaining_size: float  # 追踪剩余仓位数量


# -------- Stream 指令模型 --------
class StreamAction(str, Enum):
    add = "add"
    amend = "amend"
    cancel = "cancel"

class StreamMessage(BaseModel):
    action: StreamAction
    symbol: Optional[str] = None
    userref: Optional[int] = None
    # 针对 add
    plan: Optional[TradePlan] = None
    # 针对 amend/cancel（优先使用 Kraken txid / order_id）
    order_id: Optional[str] = None  # Kraken 订单 txid（推荐）
    trade_id: Optional[str] = None  # 兼容旧标识（内部台账ID）
    # amend 可选字段
    new_stop_loss_price: Optional[float] = None
    new_take_profits: Optional[List[TakeProfitTarget]] = None


# -------- 精简订单台账（Stream 驱动场景） --------
class MinimalTradeEntry(BaseModel):
    group_id: str
    symbol: str
    status: str = "PENDING"
    entry_txid: Optional[str] = None
    stop_loss_txid: Optional[str] = None
    stop_loss_trigger_price: Optional[float] = None
    remaining_size: Optional[float] = None
    last_event_at: Optional[float] = None