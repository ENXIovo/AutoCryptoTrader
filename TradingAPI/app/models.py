from pydantic import BaseModel, Field
from typing import Optional, Union


# -----------------
# Add Order Models
# -----------------
class AddOrderRequest(BaseModel):
    nonce: Optional[int] = None
    userref: Optional[int] = None
    cl_ord_id: Optional[str] = None

    ordertype: str = Field(..., example="limit")
    type: str = Field(..., example="buy")
    volume: str = Field(..., example="1.25")
    pair: str = Field(..., example="XBT/USD")

    price: Optional[str] = None
    price2: Optional[str] = None
    displayvol: Optional[str] = None
    leverage: Optional[str] = None
    trigger: Optional[str] = None
    reduce_only: Optional[bool] = None
    stptype: Optional[str] = None
    oflags: Optional[str] = None
    timeinforce: Optional[str] = None
    starttm: Optional[str] = None
    expiretm: Optional[str] = None
    validate: Optional[bool] = None

    # close[ordertype], close[price], close[price2] 等字段
    # 可以用更灵活的方式表示，但这里为了简单可先省略或写为dict


class AddOrderResponse(BaseModel):
    error: list
    result: dict


# -------------------
# Amend Order Models
# -------------------
class AmendOrderRequest(BaseModel):
    nonce: Optional[int] = None
    txid: Optional[str] = None
    cl_ord_id: Optional[str] = None

    order_qty: Optional[str] = None
    display_qty: Optional[str] = None
    limit_price: Optional[str] = None
    trigger_price: Optional[str] = None
    post_only: Optional[bool] = None
    deadline: Optional[str] = None


class AmendOrderResponse(BaseModel):
    error: list
    result: dict


# --------------------
# Cancel Order Models
# --------------------
class CancelOrderRequest(BaseModel):
    nonce: Optional[int] = None
    txid: Union[None, str, int] = None  # txid 可能是字符串或整型(如果用userref)
    cl_ord_id: Optional[str] = None


class CancelOrderResponse(BaseModel):
    error: list
    result: dict

