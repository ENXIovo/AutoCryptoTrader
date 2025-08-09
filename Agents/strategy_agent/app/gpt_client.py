import requests
from pydantic import ValidationError
from .models import MessageRequest, MessageResponse

class GPTClient:
    """
    仅负责跟 GPT-Proxy HTTP 通信
    """
    def __init__(self, base_url: str):
        self.base_url = base_url

    def send_message(self, req: MessageRequest) -> MessageResponse:
        payload = req.to_payload()
        try:
            resp = requests.post(self.base_url, json=payload, timeout=600)
            resp.raise_for_status()
            data = resp.json()
            # 校验并解析成强类型 MessageResponse
            return MessageResponse(**data)
        except requests.RequestException as e:
            raise RuntimeError(f"GPT request failed: {e}")
        except ValidationError as ve:
            raise RuntimeError(f"Invalid GPT-Proxy response format: {ve}")
