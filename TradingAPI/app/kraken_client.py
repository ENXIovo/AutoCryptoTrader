import time
import base64
import hashlib
import hmac
import urllib.parse
import requests

from app.config import settings


class KrakenClient:
    def __init__(self,
                 api_url: str = settings.KRAKEN_API_URL,
                 api_key: str = settings.KRAKEN_API_KEY,
                 api_secret: str = settings.KRAKEN_API_SECRET):
        self.api_url = api_url
        self.api_key = api_key
        self.api_secret = api_secret

    def _get_kraken_signature(self, url_path: str, data: dict) -> str:
        """使用 HMAC-SHA512 对请求进行签名"""
        post_data = urllib.parse.urlencode(data)
        encoded = (str(data['nonce']) + post_data).encode()
        message = url_path.encode() + hashlib.sha256(encoded).digest()

        secret = base64.b64decode(self.api_secret)
        signature = hmac.new(secret, message, hashlib.sha512)
        sig_digest = base64.b64encode(signature.digest())
        return sig_digest.decode()

    def _private_request(self, method: str, endpoint: str, data: dict) -> dict:
        """
        发送私有请求到 Kraken 服务器。
        :param method: HTTP 请求方法 (POST / GET)
        :param endpoint: API 端点 (例如 /0/private/AddOrder)
        :param data: 请求体 (dict)
        :return: 响应数据 (dict)
        """
        url = self.api_url + endpoint

        # 确保 data 中有 nonce
        if "nonce" not in data:
            data["nonce"] = int(time.time() * 1000)

        headers = {
            'API-Key': self.api_key,
            'API-Sign': self._get_kraken_signature(endpoint, data)
        }

        if method.upper() == "POST":
            resp = requests.post(url, headers=headers, data=data)
        else:
            # Kraken 大多数私有接口使用 POST，这里仅示例
            resp = requests.get(url, headers=headers, params=data)

        resp.raise_for_status()  # 如果 HTTP 状态码 != 200，会抛出异常
        return resp.json()

    def add_order(self, payload: dict) -> dict:
        """
        调用 Kraken 的 AddOrder 接口
        文档: https://api.kraken.com/0/private/AddOrder
        """
        endpoint = "/0/private/AddOrder"
        return self._private_request("POST", endpoint, payload)

    def amend_order(self, payload: dict) -> dict:
        """
        调用 Kraken 的 AmendOrder 接口
        文档: https://api.kraken.com/0/private/AmendOrder
        """
        endpoint = "/0/private/AmendOrder"
        return self._private_request("POST", endpoint, payload)

    def cancel_order(self, payload: dict) -> dict:
        """
        调用 Kraken 的 CancelOrder 接口
        文档: https://api.kraken.com/0/private/CancelOrder
        """
        endpoint = "/0/private/CancelOrder"
        return self._private_request("POST", endpoint, payload)
