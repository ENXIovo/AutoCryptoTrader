# kraken_client.py

import requests
from app.config import settings

def get_ticker(symbol: str = "XBTUSDT") -> dict:
    """
    获取最新成交价格、24h 最高、最低、成交量等信息
    对应 Kraken API: /0/public/Ticker
    """
    url = f"{settings.KRAKEN_API_URL}/Ticker"
    params = {"pair": symbol}
    resp = requests.get(url, params=params, timeout=10)
    resp.raise_for_status()
    data = resp.json()
    if data.get("error"):
        raise ValueError(f"Kraken API Error: {data['error']}")
    return data["result"]

def get_order_book(symbol: str = "XBTUSDT", depth: int = 10) -> dict:
    """
    获取订单簿 (买卖挂单) 的前 depth 档
    对应 Kraken API: /0/public/Depth
    """
    url = f"{settings.KRAKEN_API_URL}/Depth"
    params = {"pair": symbol, "count": depth}
    resp = requests.get(url, params=params, timeout=10)
    resp.raise_for_status()
    data = resp.json()
    if data.get("error"):
        raise ValueError(f"Kraken API Error: {data['error']}")
    return data["result"]

def get_ohlc(symbol: str = "XBTUSDT", interval: int = 1) -> dict:
    """
    获取 K 线数据 (OHLC)
    interval 单位为分钟, 常见 1, 5, 15, 30, 60, 240, 1440 (1d) 等
    对应 Kraken API: /0/public/OHLC
    """
    url = f"{settings.KRAKEN_API_URL}/OHLC"
    params = {"pair": symbol, "interval": interval}
    resp = requests.get(url, params=params, timeout=10)
    resp.raise_for_status()
    data = resp.json()
    if data.get("error"):
        raise ValueError(f"Kraken API Error: {data['error']}")
    return data["result"]

def get_recent_trades(symbol: str = "XBTUSDT") -> dict:
    """
    获取最近的市场成交记录
    对应 Kraken API: /0/public/Trades
    """
    url = f"{settings.KRAKEN_API_URL}/Trades"
    params = {"pair": symbol}
    resp = requests.get(url, params=params, timeout=10)
    resp.raise_for_status()
    data = resp.json()
    if data.get("error"):
        raise ValueError(f"Kraken API Error: {data['error']}")
    return data["result"]
