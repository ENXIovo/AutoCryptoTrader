import requests
from typing import List, Dict, Optional
from .config import settings

class ToolRouter:
    """
    只负责调用外部服务（如 Crypto News Collector）
    """
    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")

    def latest_news(
        self,
        limit: int = 100,
        channel: Optional[str] = None,
        keyword: Optional[str] = None,
    ) -> List[Dict]:
        params: Dict[str, object] = {"limit": limit}
        if channel:
            params["channel"] = channel
        if keyword:
            params["keyword"] = keyword

        try:
            resp = requests.get(f"{self.base_url}/news-latest", params=params, timeout=5)
            resp.raise_for_status()
            return resp.json()
        except requests.RequestException as e:
            raise RuntimeError(f"latest_news 调用失败: {e}")

    def kraken_filter(symbol: str) -> dict:
        """查询账户中指定币种的余额、挂单与可交易金额等信息。

        参数:
            symbol: 币种符号，例如 DOGE、ETH、BTC 等。

        返回:
            由 KrakenService 返回的 JSON 数据。若请求失败，则抛出运行时异常。
        """
        try:
            resp = requests.get(
                f"{settings.kraken_service_url}/kraken-filter",
                params={"symbol": symbol},
                timeout=5,
            )
            resp.raise_for_status()
            return resp.json()
        except requests.RequestException as e:
            raise RuntimeError(f"kraken_filter 调用失败: {e}")


    def gpt_latest(symbol: str) -> dict:
        """获取某币种最近一分钟的 K 线数据及技术指标。

        参数:
            symbol: 币种符号，例如 DOGE、ETH、BTC 等。

        返回:
            由 DataCollector 返回的 JSON 数据。如果 Redis 缓存中没有数据，
            则返回的消息中将指明不存在对应币种的数据。
        """
        try:
            # 构建 url 时，symbol 已经作为路径参数
            resp = requests.get(
                f"{settings.data_service_url}/gpt-latest/{symbol}",
                timeout=5,
            )
            resp.raise_for_status()
            return resp.json()
        except requests.RequestException as e:
            raise RuntimeError(f"gpt_latest 调用失败: {e}")