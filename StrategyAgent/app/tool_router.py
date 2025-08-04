import requests

# Kraken 客户端
class KrakenClient:
    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")

    def getAccountInfo(self, symbol: str) -> dict:
        resp = requests.get(f"{self.base_url}/kraken-filter", params={"symbol": symbol}, timeout=5)
        resp.raise_for_status()
        return resp.json()

# 数据采集客户端
class DataClient:
    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")

    def getKlineIndicators(self, symbol: str) -> dict:
        resp = requests.get(f"{self.base_url}/gpt-latest/{symbol}", timeout=5)
        resp.raise_for_status()
        return resp.json()

# 新闻客户端
class NewsClient:
    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")

    def getCryptoNews(self, limit: int, channel: str | None = None, keyword: str | None = None) -> list[dict]:
        params = {"limit": limit}
        if channel:
            params["channel"] = channel
        if keyword:
            params["keyword"] = keyword
        resp = requests.get(f"{self.base_url}/news-latest", params=params, timeout=5)
        resp.raise_for_status()
        return resp.json()
