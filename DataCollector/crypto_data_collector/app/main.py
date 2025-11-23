# app/main.py
import os
import json
from contextlib import asynccontextmanager

from fastapi import FastAPI, Query
import redis
from celery.result import AsyncResult

from app import db
from app.tasks import fetch_and_store_data_for_intervals

redis_client = redis.Redis(host='redis-server', port=6379, decode_responses=True)

@asynccontextmanager
async def lifespan(app: FastAPI):
    if os.getenv("ENV", "development") == "development":
        db.Base.metadata.create_all(bind=db.engine)
        print("Startup: Database tables created.")
    yield
    print("Shutdown: Cleaning up resources...")

app = FastAPI(
    title="Kraken Data Collector",
    lifespan=lifespan
)

@app.get("/")
def read_root():
    return {"message": "Kraken Data Collector is running"}

@app.get("/start-collection/{symbol}")
def start_collection(
    symbol: str = "XBTUSDT",
    intervals: str = Query("15,60,240,1440", description="Comma-separated intervals, e.g. '15,60,240,1440'")
):
    """
    例如调用: 
    GET /start-collection/XBTUSDT?intervals=15,60,240,1440
    即可一次性获取 XBTUSDT 的 15m, 1h, 4h, 1d 数据
    """
    # 解析 intervals 字符串 -> list[int]
    interval_list = [int(x.strip()) for x in intervals.split(",") if x.strip().isdigit()]
    # 触发 Celery 任务
    task = fetch_and_store_data_for_intervals.delay(symbol, interval_list)

    # 这里返回一个 Task ID
    return {
        "message": f"Data collection tasks for {symbol} triggered",
        "intervals": interval_list,
        "task_id": task.id
    }

@app.get("/task-result/{task_id}")
def get_task_result(task_id: str):
    result = AsyncResult(task_id, app=fetch_and_store_data_for_intervals)
    if result.state == "PENDING":
        return {"state": "PENDING", "result": None}
    elif result.state != "FAILURE":
        return {
            "state": result.state,
            "result": result.result  # 这里就是上面return的gpt_data
        }
    else:
        return {"state": "FAILURE", "result": str(result.result)}

@app.get("/gpt-latest/{symbol}")
def get_gpt_data(symbol: str):
    redis_key = f"data:{symbol}"
    cached_data = redis_client.get(redis_key)
    if cached_data:
        return json.loads(cached_data)
    else:
        return {"message": f"No GPT data found for symbol={symbol} in Redis."}