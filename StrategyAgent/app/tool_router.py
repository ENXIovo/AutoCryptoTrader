import requests
from typing import List, Dict, Optional

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
