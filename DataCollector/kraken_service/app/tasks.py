# app/tasks.py

import time
import hmac
import hashlib
import base64
import urllib.parse
import requests
import redis
import json
from celery import Celery
from celery.schedules import crontab

from app.config import settings

# ================== 初始化 Redis ==================
redis_client = redis.Redis(
    host=settings.REDIS_HOST,
    port=settings.REDIS_PORT,
    decode_responses=True,
    db=0
)

# ================== 初始化 Celery ==================
celery_app = Celery(
    "kraken_tasks",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
)

# Celery Beat 配置：每分钟执行一次，并指定使用 kraken_queue
celery_app.conf.beat_schedule = {
    "fetch-kraken-data-every-minute": {
        "task": "app.tasks.fetch_and_store_kraken_data",
        "schedule": crontab(minute="*"),
        "options": {"queue": "kraken_queue"}  # 指定队列
    },
}
celery_app.conf.timezone = "UTC"

# ================== Kraken API工具函数 ==================
def generate_api_sign(uri_path, payload, api_secret):
    payload_str = urllib.parse.urlencode(payload)
    message = (payload['nonce'] + payload_str).encode()
    sha256_digest = hashlib.sha256(message).digest()
    hmac_digest = hmac.new(
        base64.b64decode(api_secret),
        uri_path.encode() + sha256_digest,
        hashlib.sha512
    ).digest()
    return base64.b64encode(hmac_digest).decode()

def kraken_request(api_key, api_secret, uri_path, payload=None, method="POST"):
    """
    封装访问 Kraken API 的请求
    - 对私有接口执行 POST
    - 对公共接口（如 Get Tradable Asset Pairs）使用 GET
    """
    if payload is None:
        payload = {}

    if method == "POST":
        url = settings.KRAKEN_API_URL + uri_path
        payload['nonce'] = str(int(time.time() * 1000))
        api_sign = generate_api_sign(uri_path, payload, api_secret)
        headers = {
            "API-Key": api_key,
            "API-Sign": api_sign,
            "Content-Type": "application/x-www-form-urlencoded"
        }
        response = requests.post(url, headers=headers, data=urllib.parse.urlencode(payload))
    else:
        # GET 请求，如获取可交易对
        url = settings.KRAKEN_API_URL + uri_path
        response = requests.get(url)

    response.raise_for_status()
    return response.json()

def get_open_orders(api_key, api_secret):
    uri_path = "/0/private/OpenOrders"
    payload = {"trades": True}
    return kraken_request(api_key, api_secret, uri_path, payload=payload, method="POST")

def get_account_balance(api_key, api_secret):
    uri_path = "/0/private/Balance"
    return kraken_request(api_key, api_secret, uri_path, payload={}, method="POST")

def get_trade_history(api_key, api_secret, start=None, end=None):
    uri_path = "/0/private/TradesHistory"
    payload = {"trades": True}
    if start:
        payload["start"] = start
    if end:
        payload["end"] = end
    return kraken_request(api_key, api_secret, uri_path, payload=payload, method="POST")

def get_asset_pairs():
    """
    调用 Kraken 公共接口 /0/public/AssetPairs
    获取所有可交易资产对。
    """
    uri_path = "/0/public/AssetPairs"
    # 公共接口不需要 API Key / Secret
    response = requests.get(settings.KRAKEN_API_URL + uri_path, timeout=10)
    response.raise_for_status()
    data = response.json()
    return data

def format_open_orders(raw_open_orders):
    orders = raw_open_orders.get('result', {}).get('open', {})
    formatted_orders = {}
    for order_id, details in orders.items():
        pair = details['descr']['pair']
        if pair not in formatted_orders:
            formatted_orders[pair] = []
        formatted_orders[pair].append({
            "order_id": order_id,
            "pair": details['descr']['pair'],
            "type": details['descr']['type'],
            "ordertype": details['descr']['ordertype'],
            "price": details['descr']['price'],
            "vol": details['vol'],
            "vol_exec": details['vol_exec'],
            "status": details['status'],
            "opentm": int(details['opentm'])
        })
    return formatted_orders


def format_account_balance(raw_balance):
    return raw_balance.get('result', {})

def format_trade_history(raw_trade_history):
    trades = raw_trade_history.get('result', {}).get('trades', {})
    formatted_trades = {}
    for trade_id, details in trades.items():
        pair = details.get("pair", "unknown")
        if pair not in formatted_trades:
            formatted_trades[pair] = []
        
        formatted_trades[pair].append({
            "trade_id": trade_id,
            "ordertxid": details.get("ordertxid"),
            "time": int(details.get("time", 0)),
            "type": details.get("type"),
            "ordertype": details.get("ordertype"),
            "price": details.get("price"),
            "vol": details.get("vol"),
            "cost": details.get("cost"),
            "fee": details.get("fee"),
            "margin": details.get("margin"),
            "misc": details.get("misc"),
        })
    
    return formatted_trades

def get_trade_balance(api_key, api_secret, asset="ZUSD"):
    """
    调用 Kraken 私有接口 /0/private/TradeBalance 获取账户的交易余额信息
    """
    uri_path = "/0/private/TradeBalance"
    payload = {"asset": asset}
    return kraken_request(api_key, api_secret, uri_path, payload=payload, method="POST")


# ================== 新增的辅助函数 ==================

def get_filtered_data(symbol: str) -> dict:
    """
    根据输入的 symbol，通过 Kraken 公共接口获取 altname，
    然后在 Redis 数据中过滤相关信息。
    """
    # 1) 获取指定资产信息，提取 altname
    asset_url = f"{settings.KRAKEN_API_URL}/0/public/Assets?asset={symbol.upper()}"
    resp = requests.get(asset_url, timeout=10)
    resp.raise_for_status()
    asset_data = resp.json()
    if asset_data.get("error"):
        raise RuntimeError(f"Error in /public/Assets: {asset_data['error']}")
    
    result = asset_data.get("result", {})
    if not result:
        raise ValueError(f"No asset information found for symbol '{symbol}'")
    
    base_key = list(result.keys())[0]        # 获取结果中的第一个键，作为基础货币代码
    asset_info = result[base_key]            # 获取对应的资产信息
    altname = asset_info.get("altname")      # 获取别名（altname）
    print(f"Base Key: {base_key}, Altname: {altname}")
    
    # 2) 从 Redis 读取主数据和交易历史
    main_hash_key = "kraken_data:main"
    trade_hash_key = "kraken_data:trade_history"

    if not redis_client.exists(main_hash_key):
        raise RuntimeError("No main data found in Redis. Please run /start-collection first.")
    main_data = redis_client.hgetall(main_hash_key)
    open_orders = json.loads(main_data.get("open_orders", "[]"))
    account_balance = json.loads(main_data.get("account_balance", "{}"))
    trade_balance = json.loads(main_data.get("trade_balance", "{}"))

    trade_map = {}
    if redis_client.exists(trade_hash_key):
        trade_map = redis_client.hgetall(trade_hash_key)

    # 3) 过滤逻辑
    # a) 账户余额：保留与 altname 匹配的资产和稳定币
    # stable_quotes = "USD"
    # relevant_terms = [base_key, altname, stable_quotes]
    # filtered_balance = {
    #     asset: amount
    #     for asset, amount in account_balance.items()
    #     if any(term in asset for term in relevant_terms)
    # }

    # b) 过滤交易历史：只保留交易对中包含 altname 的记录
    filtered_trade_history = {}
    for key, trades_json in trade_map.items():
        # 如果交易对键中包含 altname，则保留
        if altname in key or base_key in key:
            filtered_trade_history[key] = json.loads(trades_json)

    # c) 过滤挂单：只保留与 altname 相关的挂单
    # filtered_orders = [
    #     order for order in open_orders
    #     if altname in order.get("pair", "") or base_key in order.get("pair", "")
    # ]

    # d) 置换trade_balance名字
    trade_balance_renamed = {
        "equivalent_balance": trade_balance.get("eb", ""),
        "trade_balance": trade_balance.get("tb", ""),
        "margin": trade_balance.get("m", ""),
        "unrealized_pnl": trade_balance.get("n", ""),
        "cost_basis": trade_balance.get("c", ""),
        "valuation": trade_balance.get("v", ""),
        "equity": trade_balance.get("e", ""),
        "free_margin": trade_balance.get("mf", ""),
        "margin_level": trade_balance.get("ml", ""),
        "unexecuted_value": trade_balance.get("uv", "")
    }

    # 4) 返回结果
    return {
        "symbol_request": symbol,
        "altname": altname,
        "balance": account_balance,
        "trade_balance": trade_balance_renamed,
        "open_orders": open_orders,
        "trade_history": filtered_trade_history,
    }


# ========== 核心封装：获取所有数据并格式化 ==========
def get_all_kraken_data():
    """
    一次性获取挂单、账户余额、交易历史以及可交易资产对并进行相应格式化。
    """
    try:
        # 1) 挂单和账户余额（私有接口，需要 key/secret）
        open_orders_raw = get_open_orders(settings.KRAKEN_API_KEY, settings.KRAKEN_API_SECRET)
        account_balance_raw = get_account_balance(settings.KRAKEN_API_KEY, settings.KRAKEN_API_SECRET)

        # 2) 交易历史（私有接口）
        raw_trade_history = get_trade_history(settings.KRAKEN_API_KEY, settings.KRAKEN_API_SECRET)
        
        # 3) 获取交易余额
        trade_balance_raw = get_trade_balance(settings.KRAKEN_API_KEY, settings.KRAKEN_API_SECRET)

        # 4) 可交易资产对（公共接口，不需要 key/secret）
        raw_asset_pairs = get_asset_pairs()

        # 5) 统一格式化
        formatted_data = {
            "open_orders": format_open_orders(open_orders_raw),
            "account_balance": format_account_balance(account_balance_raw),
            "trade_balance": trade_balance_raw.get("result", {}),
            "trade_history": format_trade_history(raw_trade_history),
            "asset_pairs": raw_asset_pairs.get("result", {})
        }
        return formatted_data

    except Exception as e:
        raise RuntimeError(f"Failed to fetch and format all Kraken data: {str(e)}")


# ================== Celery 任务定义 ==================
@celery_app.task(queue="kraken_queue")
def fetch_and_store_kraken_data():
    """
    每分钟自动执行的定时任务：
    从 Kraken API 获取 open orders、balance、交易历史和可交易资产对，并以“文件夹/层次化”方式存储到 Redis。
    """
    try:
        data = get_all_kraken_data()

        # 1. 用 Hash 结构存储 "kraken_data:main"（统一存储主数据）
        #    - open_orders, account_balance, asset_pairs 等
        main_hash_key = "kraken_data:main"
        redis_client.hset(main_hash_key, "open_orders", json.dumps(data["open_orders"]))
        redis_client.hset(main_hash_key, "account_balance", json.dumps(data["account_balance"]))
        redis_client.hset(main_hash_key, "trade_balance", json.dumps(data["trade_balance"]))
        # 注意：我们不存 trade_history 在这里，因为要单独分开

        # 设置过期时间，比如 5 分钟
        redis_client.expire(main_hash_key, 300)

        # 2. 用另一个 Hash 存储 "kraken_data:trade_history"
        #    对于每个 symbol 做一个 field
        trade_hash_key = "kraken_data:trade_history"
        for symbol, trades in data["trade_history"].items():
            redis_client.hset(trade_hash_key, symbol, json.dumps(trades))
        # 给 trade_history 整体设置过期 1 小时
        redis_client.expire(trade_hash_key, 3600)

        print(f"[Celery] (HASH) Fetched & stored all Kraken data at {time.ctime()}")
    except Exception as e:
        print(f"[Celery] Error while fetching/storing Kraken data: {e}")


@celery_app.task(queue="kraken_queue")
def fetch_and_store_data_on_demand():
    """
    手动触发的任务：与定时任务相同逻辑，获取所有数据并以层次化方式存储到 Redis。
    """
    try:
        data = get_all_kraken_data()

        # 1. 主数据存储到 Hash => kraken_data_on_demand:main
        main_hash_key = "kraken_data_on_demand:main"
        redis_client.hset(main_hash_key, "open_orders", json.dumps(data["open_orders"]))
        redis_client.hset(main_hash_key, "account_balance", json.dumps(data["account_balance"]))
        redis_client.hset(main_hash_key, "trade_balance", json.dumps(data["trade_balance"]))
        redis_client.hset(main_hash_key, "asset_pairs", json.dumps(data["asset_pairs"]))
        redis_client.expire(main_hash_key, 300)

        # 2. 交易历史 => kraken_data_on_demand:trade_history
        trade_hash_key = "kraken_data_on_demand:trade_history"
        for symbol, trades in data["trade_history"].items():
            redis_client.hset(trade_hash_key, symbol, json.dumps(trades))
        redis_client.expire(trade_hash_key, 3600)

        print(f"[Celery] On-demand data stored at {time.ctime()}")
        return data
    except Exception as e:
        return {"error": str(e)}
