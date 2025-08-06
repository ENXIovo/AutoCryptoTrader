import time

from app.kraken_client import KrakenClient
from app.models import (
    AddOrderRequest, AddOrderResponse,
    AmendOrderRequest, AmendOrderResponse,
    CancelOrderRequest, CancelOrderResponse,
)

client = KrakenClient()


# ----------------  下   单  ----------------
def add_order_service(payload: AddOrderRequest) -> AddOrderResponse:
    pl_dict = payload.model_dump(
        by_alias=True,
        mode="json",
        exclude_none=True,
    )
    pl_dict.setdefault("userref", int(time.time()))
    print(pl_dict)
    resp = client.add_order(pl_dict)
    if resp["error"]:
        raise RuntimeError(f"Kraken add order failed: {resp['error']}")
    return AddOrderResponse(**resp)


# ----------------  改   单  ----------------
def amend_order_service(payload: AmendOrderRequest) -> AmendOrderResponse:
    """
    调 AmendOrder
    """
    resp = client.amend_order(
        payload.model_dump(exclude_none=True)   # 不需要 alias
    )
    if resp["error"]:
        raise RuntimeError(f"Kraken amend order failed: {resp['error']}")
    return AmendOrderResponse(**resp)


# ----------------  撤   单  ----------------
def cancel_order_service(payload: CancelOrderRequest) -> CancelOrderResponse:
    """
    调 CancelOrder
    """
    resp = client.cancel_order(
        payload.model_dump(exclude_none=True)
    )
    if resp["error"]:
        raise RuntimeError(f"Kraken cancel order failed: {resp['error']}")
    return CancelOrderResponse(**resp)
