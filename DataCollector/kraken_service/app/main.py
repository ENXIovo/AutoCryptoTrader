# app/main.py

import json
import redis
import requests
import humanize
from fastapi import FastAPI, Query, HTTPException
from celery.result import AsyncResult
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from app.config import settings, LOCAL_TZ
from app.tasks import celery_app, fetch_and_store_data_on_demand, get_filtered_data

app = FastAPI(title="Kraken Service")

redis_client = redis.Redis(
    host=settings.REDIS_HOST,
    port=settings.REDIS_PORT,
    decode_responses=True,
    db=0
)

@app.get("/")
def read_root():
    return {"message": "Kraken Data Service is running"}

@app.get("/kraken-latest")
def get_latest_kraken_data():
    """
    从 Redis (Hash) 中读取最近一次 Celery 任务存储的 Kraken 数据
      - Hash: kraken_data:main -> open_orders, account_balance, asset_pairs
      - Hash: kraken_data:trade_history -> 每个 symbol 的交易历史
    """

    main_hash_key = "kraken_data:main"
    trade_hash_key = "kraken_data:trade_history"

    # 如果主数据不存在，直接返回
    if not redis_client.exists(main_hash_key):
        return {"message": "No Kraken data available"}

    # 读取主数据 (Hash 的所有 field)
    main_data = redis_client.hgetall(main_hash_key)
    result_dict = {
        "server_time_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "server_time_local": datetime.now(ZoneInfo(LOCAL_TZ)).isoformat(),
    }

    # 解析主数据中各字段的 JSON
    # open_orders
    if "open_orders" in main_data:
        result_dict["open_orders"] = json.loads(main_data["open_orders"])
    # account_balance
    if "account_balance" in main_data:
        result_dict["account_balance"] = json.loads(main_data["account_balance"])
    # trade_balance
    if "trade_balance" in main_data:
        result_dict["trade_balance"] = json.loads(main_data["trade_balance"])

    # 读取 trade_history 散列
    if redis_client.exists(trade_hash_key):
        trade_map = redis_client.hgetall(trade_hash_key)  # {symbol1: jsonStr, symbol2: jsonStr}
        parsed_trades = {}
        for symbol, trade_str in trade_map.items():
            parsed_trades[symbol] = json.loads(trade_str)
        result_dict["trade_history"] = parsed_trades
    else:
        result_dict["trade_history"] = {}

    return result_dict

@app.get("/start-collection")
def start_collection():
    """
    手动触发一次 Celery 任务, 返回Task ID, 观察执行结果
    """
    task = fetch_and_store_data_on_demand.delay()
    return {
        "message": "On-demand Kraken data collection triggered",
        "task_id": task.id
    }

@app.get("/task-result/{task_id}")
def get_task_result(task_id: str):
    """
    根据 task_id 查询 Celery 任务执行结果
    """
    result = AsyncResult(task_id, app=celery_app)
    if result.state == "PENDING":
        return {"state": "PENDING", "result": None}
    elif result.state == "STARTED":
        return {"state": "STARTED", "result": None}
    elif result.state == "SUCCESS":
        return {"state": result.state, "result": result.result}
    elif result.state == "FAILURE":
        return {"state": result.state, "result": str(result.result)}
    else:
        return {"state": result.state, "result": None}

@app.get("/kraken-filter")
def get_filtered_kraken_data(symbol: str = Query(..., description="例如：DOGE, ETH, BTC 等")):
    try:
        return get_filtered_data(symbol)
    except Exception as e:
        # 捕获在 tasks.py 中发生的异常，并返回 HTTP 错误
        raise HTTPException(status_code=500, detail=str(e))

