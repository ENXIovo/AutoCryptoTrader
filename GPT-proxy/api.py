# api.py
from fastapi import FastAPI, HTTPException, Request, status
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from schemas.chat_schemas import ErrorResponse
from services.redis_store import RedisStore
from services.session_manager import SessionManager
from apis.api_manager_factory import APIManagerFactory

import logging

# tracemalloc.start()  # 开始追踪内存分配

app = FastAPI()

@app.on_event("startup")
def startup_event():
    # 初始化所有API客户端实例
    APIManagerFactory.initialize_clients()
    app.state.redis_store = RedisStore()
    app.state.session_manager = SessionManager(app.state.redis_store)

@app.on_event("shutdown")
async def shutdown_event():
    await app.state.redis_store.close()


# 处理 HTTP 异常
@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    logging.error(f"HTTP error: {exc.detail}")
    return JSONResponse(
        status_code=exc.status_code,
        content=ErrorResponse(code=exc.status_code, message=exc.detail).model_dump(),
    )

# 处理请求验证错误
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    errors = [
        {"loc": e["loc"], "msg": e["msg"], "type": e["type"]} for e in exc.errors()
    ]
    logging.error(f"Validation error: {errors}")
    error_message = "Validation error on fields: " + "; ".join(
        [f"{e['loc'][1]}: {e['msg']}" for e in errors]
    )
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content=ErrorResponse(code=status.HTTP_422_UNPROCESSABLE_ENTITY, message=error_message).model_dump(),
    )


# 处理其他未捕获的异常
@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    logging.error(f"Unhandled error: {str(exc)}")
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=ErrorResponse(code=status.HTTP_500_INTERNAL_SERVER_ERROR, message="Internal Server Error").model_dump(),
    )

from handlers.routes import router as gpt_router
# 将router整合到主应用中
app.include_router(gpt_router, prefix="/api", tags=["gpt"])

# python -m uvicorn api:app --reload
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
