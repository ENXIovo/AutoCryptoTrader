from app.kraken_client import KrakenClient
from app.models import (
    AddOrderRequest, AddOrderResponse,
    AmendOrderRequest, AmendOrderResponse,
    CancelOrderRequest, CancelOrderResponse
)

client = KrakenClient()


def add_order_service(payload: AddOrderRequest) -> AddOrderResponse:
    """
    下单服务逻辑，调用 KrakenClient.add_order
    """
    # 转换为 dict 并传给 client
    resp = client.add_order(payload.dict(exclude_none=True))
    return AddOrderResponse(**resp)


def amend_order_service(payload: AmendOrderRequest) -> AmendOrderResponse:
    """
    改单服务逻辑，调用 KrakenClient.amend_order
    """
    resp = client.amend_order(payload.dict(exclude_none=True))
    return AmendOrderResponse(**resp)


def cancel_order_service(payload: CancelOrderRequest) -> CancelOrderResponse:
    """
    撤单服务逻辑，调用 KrakenClient.cancel_order
    """
    resp = client.cancel_order(payload.dict(exclude_none=True))
    return CancelOrderResponse(**resp)
