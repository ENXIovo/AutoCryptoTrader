# app/binance_client.py

import requests
from app.config import settings

def get_price(symbol: str = "BTCUSDT") -> dict:
    """
    获取最新成交价格: /api/v3/ticker/price
    返回示例: {"symbol": "BTCUSDT", "price": "20835.12"}
    """
    url = f"{settings.BINANCE_API_URL}/ticker/price"
    params = {"symbol": symbol}
    resp = requests.get(url, params=params, timeout=10)
    resp.raise_for_status()
    return resp.json()  # dict: {"symbol": ..., "price": ...}

def get_book_ticker(symbol: str = "BTCUSDT") -> dict:
    """
    获取订单簿中最优买卖价: /api/v3/ticker/bookTicker
    返回示例: {"symbol": "BTCUSDT","bidPrice":"100","askPrice":"101",...}
    """
    url = f"{settings.BINANCE_API_URL}/ticker/bookTicker"
    params = {"symbol": symbol}
    resp = requests.get(url, params=params, timeout=10)
    resp.raise_for_status()
    return resp.json()

def get_24hr_ticker(symbol: str = "BTCUSDT") -> dict:
    """
    获取过去24小时的价格变动数据: /api/v3/ticker/24hr
    返回示例: {"symbol":"BTCUSDT","priceChange":"-94.99999800","volume":"431.00000000",...}
    """
    url = f"{settings.BINANCE_API_URL}/ticker/24hr"
    params = {"symbol": symbol}
    resp = requests.get(url, params=params, timeout=10)
    resp.raise_for_status()
    return resp.json()

def get_klines(symbol: str = "BTCUSDT", interval: str = "1m", limit: int = 50) -> list:
    """
    获取K线数据: /api/v3/klines
    返回示例: [
       [1499040000000,"0.01634790","0.80000000","0.01575800","0.01577100","148976.11427815",...],
       ...
    ]
    """
    url = f"{settings.BINANCE_API_URL}/klines"
    params = {
        "symbol": symbol,
        "interval": interval,
        "limit": limit
    }
    resp = requests.get(url, params=params, timeout=10)
    resp.raise_for_status()
    return resp.json()

def get_depth(symbol: str = "BTCUSDT", limit: int = 10) -> dict:
    """
    获取订单簿深度: /api/v3/depth
    返回示例: {"bids": [["4.0", "431"], ...], "asks": [["4.2", "12"], ...]}
    """
    url = f"{settings.BINANCE_API_URL}/depth"
    params = {"symbol": symbol, "limit": limit}
    resp = requests.get(url, params=params, timeout=10)
    resp.raise_for_status()
    return resp.json()

def get_avg_price(symbol: str = "BTCUSDT") -> dict:
    """
    获取最近5分钟的加权平均价格: /api/v3/avgPrice
    返回示例: {"mins": 5, "price": "9.35751834"}
    """
    url = f"{settings.BINANCE_API_URL}/avgPrice"
    params = {"symbol": symbol}
    resp = requests.get(url, params=params, timeout=10)
    resp.raise_for_status()
    return resp.json()

def get_trades(symbol: str = "BTCUSDT", limit: int = 10) -> list:
    """
    获取最近市场成交记录: /api/v3/trades
    返回示例: [{"price": "4.0", "qty": "12", ...}, ...]
    """
    url = f"{settings.BINANCE_API_URL}/trades"
    params = {"symbol": symbol, "limit": limit}
    resp = requests.get(url, params=params, timeout=10)
    resp.raise_for_status()
    return resp.json()
