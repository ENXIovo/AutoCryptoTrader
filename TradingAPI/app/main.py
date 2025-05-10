from fastapi import FastAPI, HTTPException
from app.models import (
    AddOrderRequest, AddOrderResponse,
    AmendOrderRequest, AmendOrderResponse,
    CancelOrderRequest, CancelOrderResponse
)
from app.services import (
    add_order_service,
    amend_order_service,
    cancel_order_service
)

app = FastAPI(
    title="Kraken API Proxy Service",
    description="一个简单的Kraken代理服务示例",
    version="1.0.0"
)

@app.post("/orders/add", response_model=AddOrderResponse)
def add_order_endpoint(payload: AddOrderRequest):
    try:
        result = add_order_service(payload)
        return result
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/orders/amend", response_model=AmendOrderResponse)
def amend_order_endpoint(payload: AmendOrderRequest):
    try:
        result = amend_order_service(payload)
        return result
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/orders/cancel", response_model=CancelOrderResponse)
def cancel_order_endpoint(payload: CancelOrderRequest):
    try:
        result = cancel_order_service(payload)
        return result
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8100, reload=True)
