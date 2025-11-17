import httpx
from typing import Optional

from app.config import settings


class DataClient:
    def __init__(self, base_url: Optional[str] = None, timeout: float = 10.0):
        self.base_url = (base_url or settings.DATA_SERVICE_URL).rstrip("/")
        self._client = httpx.Client(timeout=timeout)

    def get_kline_indicators(self, symbol: str) -> dict:
        resp = self._client.get(f"{self.base_url}/gpt-latest/{symbol}")
        resp.raise_for_status()
        return resp.json()

    def get_last_price(self, symbol: str) -> Optional[float]:
        try:
            data = self.get_kline_indicators(symbol)
            last = (
                ((data or {}).get("common_info") or {})
                .get("ticker", {})
                .get("last_price")
            )
            return float(last) if last is not None else None
        except Exception:
            return None


