# app/kraken_client.py
import time
import hmac
import hashlib
import base64
import httpx
import urllib.parse
from typing import Dict, Any

from app.config import settings

class KrakenClient:
    """
    一个用于与Kraken API交互的、生产级的底层异步客户端。
    它处理所有底层的认证、签名和HTTP请求。
    """
    def __init__(self):
        # 从统一的配置中加载敏感信息
        self.base_url = settings.KRAKEN_API_URL
        self.api_key = settings.KRAKEN_API_KEY
        self.api_secret = settings.KRAKEN_API_SECRET
        # 创建一个可复用的httpx客户端实例，提升性能
        self.async_client = httpx.AsyncClient()

    def _get_signature(self, uri_path: str, data: Dict[str, Any]) -> str:
        """
        根据Kraken文档生成API-Sign头。
        """
        # 1. 对POST数据进行URL编码
        postdata = urllib.parse.urlencode(data)
        
        # 2. 对(nonce + postdata)进行SHA256哈希
        encoded = (str(data['nonce']) + postdata).encode()
        message_hash = hashlib.sha256(encoded).digest()
        
        # 3. 对(uri_path + message_hash)进行HMAC-SHA512签名
        hmac_digest = hmac.new(
            base64.b64decode(self.api_secret),
            uri_path.encode() + message_hash,
            hashlib.sha512
        )
        
        # 4. 对签名结果进行Base64编码
        return base64.b64encode(hmac_digest.digest()).decode()

    async def _post(self, endpoint: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        执行一个POST请求，并处理完整的认证签名流程。
        """
        uri_path = f"/0{endpoint}"
        
        # 确保每个请求都有一个唯一的nonce
        data['nonce'] = str(int(time.time() * 1000))

        headers = {
            "API-Key": self.api_key,
            "API-Sign": self._get_signature(uri_path, data)
        }
        
        try:
            response = await self.async_client.post(
                url=f"{self.base_url}{uri_path}",
                headers=headers,
                data=data # httpx会将其自动编码为 application/x-www-form-urlencoded
            )
            # 检查HTTP状态码，如果失败（如502, 503），会抛出异常
            response.raise_for_status()
            
            # 返回Kraken服务器响应的JSON数据
            return response.json()

        except httpx.HTTPStatusError as e:
            # 处理API网关层面的错误
            print(f"HTTP Error: {e.response.status_code} for {e.request.url} - {e.response.text}")
            return {"error": [f"HTTP Error: {e.response.status_code}"], "result": {}}
        except Exception as e:
            # 处理其他意外错误，如网络问题
            print(f"An unexpected error occurred during API call: {e}")
            return {"error": [str(e)], "result": {}}

    async def add_order(self, order_data: Dict[str, Any]) -> Dict[str, Any]:
        """提交一个新订单。"""
        return await self._post("/private/AddOrder", order_data)

    async def amend_order(self, amend_data: Dict[str, Any]) -> Dict[str, Any]:
        """修改一个现有订单。"""
        return await self._post("/private/AmendOrder", amend_data)

    async def cancel_order(self, cancel_data: Dict[str, Any]) -> Dict[str, Any]:
        """取消一个现有订单。"""
        return await self._post("/private/CancelOrder", cancel_data)

    async def query_orders(self, query_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        查询一个或多个订单的状态。
        query_data 示例: {"txid": "OABC-DEFG-HIJK"}
        """
        # 增加一个参数，说明需要包含成交信息
        query_data.setdefault("trades", True)
        return await self._post("/private/QueryOrders", query_data)

    async def get_ticker(self, ticker_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        获取市场价格（公共端点，无需签名）。
        """
        pair = ticker_data.get("pair")
        if not pair:
            return {"error": ["Pair is required for get_ticker"], "result": {}}
            
        try:
            # 公共端点直接用GET请求
            response = await self.async_client.get(f"https://api.kraken.com/0/public/Ticker?pair={pair}")
            response.raise_for_status()
            # 只返回result部分，保持与其他接口的返回风格一致
            return response.json().get("result", {})
        except Exception as e:
            return {"error": [str(e)], "result": {}}