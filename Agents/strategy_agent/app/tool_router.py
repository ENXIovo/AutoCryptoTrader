import requests
from typing import Optional

# 交易所客户端 (Hyperliquid-Lite / Virtual Exchange)
class ExchangeClient:
    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")

    def getAccountInfo(self) -> dict:
        # Calls POST /info with clearinghouseState
        resp = requests.post(f"{self.base_url}/info", json={"type": "clearinghouseState"}, timeout=10)
        resp.raise_for_status()
        return resp.json()

# 数据采集客户端
class DataClient:
    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")

    def getKlineIndicators(self, symbol: str) -> dict:
        resp = requests.get(f"{self.base_url}/gpt-latest/{symbol}", timeout=10)
        resp.raise_for_status()
        return resp.json()

# 新闻客户端（新版：/top-news）
class NewsClient:
    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")

    # 保留原始接口，便于调试或后续扩展
    def getTopNewsRaw(self, limit: int, period: Optional[str] = None) -> list[dict]:
        params = {"limit": limit}
        if period is not None:
            params["period"] = period  # "day" | "week" | "month"
        resp = requests.get(f"{self.base_url}/top-news", params=params, timeout=10)
        resp.raise_for_status()
        return resp.json()

    # 对 GPT 暴露的精简视图：只保留决策必需字段
    def getTopNews(self, limit: int, period: Optional[str] = None) -> list[dict]:
        raw_items = self.getTopNewsRaw(limit=limit, period=period)

        WHITELIST = ("summary", "category", "durability", "weight", "confidence", "source", "age", "ts")

        slim_items: list[dict] = []
        for it in raw_items:
            # 只取白名单字段
            slim = {k: it.get(k) for k in WHITELIST}

            # category 统一为 list[str]（后端可能是 "regulation,macro" 或 ["regulation","macro"]）
            cats = it.get("category")
            if isinstance(cats, str):
                slim["category"] = [c.strip() for c in cats.split(",") if c.strip()]
            elif isinstance(cats, list):
                slim["category"] = [str(c).strip() for c in cats if str(c).strip()]
            else:
                slim["category"] = []

            # weight 做轻量四舍五入，节省 token（不影响排序，因为排序在服务端）
            try:
                w = float(it.get("weight", 0.0))
            except (TypeError, ValueError):
                w = 0.0
            slim["weight"] = round(w, 3)

            # 其余字段保持原样：summary/source/durability/confidence/age（"15 hours ago"）
            slim_items.append(slim)

        return slim_items
