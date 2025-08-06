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
    # ① 允许「额外字段」如 close[ordertype]，否则会在 model_dump 时被丢弃
    model_config = ConfigDict(extra="allow")

    # ─────── metadata ───────
    nonce: Optional[int] = None
    userref: Optional[int] = None
    cl_ord_id: Optional[str] = None

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
    validate: Optional[bool] = None

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


# -- AddOrder Response --
class OrderDescr(BaseModel):
    order: str
    close: Optional[str] = None


class AddOrderResult(BaseModel):
    txid: List[str]
    descr: OrderDescr


class AddOrderResponse(BaseModel):
    error: List[str]
    result: AddOrderResult


# -------- Amend Order --------
class AmendOrderRequest(BaseModel):
    """
    字段完全对齐 Kraken AmendOrder 文档。
    """
    nonce: Optional[int] = None
    txid: Optional[str] = None
    cl_ord_id: Optional[str] = None

    order_qty: Optional[str] = None          # 新数量
    display_qty: Optional[str] = None        # 冰山可见量
    limit_price: Optional[str] = None        # 新限价
    trigger_price: Optional[str] = None      # 新触发价
    post_only: Optional[bool] = None
    deadline: Optional[str] = None


class AmendOrderResult(BaseModel):
    amend_id: str


class AmendOrderResponse(BaseModel):
    error: List[str]
    result: AmendOrderResult


# -------- Cancel Order --------
class CancelOrderRequest(BaseModel):
    nonce: Optional[int] = None
    txid: Union[None, str, int] = None       # Kraken 文档允许 str 或 int
    cl_ord_id: Optional[str] = None
    userref: Optional[int] = None            # 支持批量按 userref 撤单


class CancelOrderResult(BaseModel):
    count: int
    pending: Optional[bool] = False


class CancelOrderResponse(BaseModel):
    error: List[str]
    result: CancelOrderResult
