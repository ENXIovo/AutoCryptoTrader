import requests
import time
import random
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pydantic import ValidationError
from .models import MessageRequest, MessageResponse


def utc_timestamp() -> float:
    """
    获取当前UTC时间戳（Unix timestamp）
    
    Returns:
        UTC时间戳（float）
    """
    return datetime.now(timezone.utc).timestamp()

class GPTClient:
    """
    仅负责跟 GPT-Proxy HTTP 通信
    """
    def __init__(self, base_url: str, max_retries: int = 3):
        self.base_url = base_url
        self.max_retries = max_retries

    def send_message(self, req: MessageRequest) -> MessageResponse:
        payload = req.to_payload()

        attempts = 0
        last_error: Exception | None = None

        while attempts < self.max_retries:
            attempts += 1
            try:
                resp = requests.post(self.base_url, json=payload)

                # 429: 退避到 TPM 刷新（或遵循 Retry-After）
                if resp.status_code == 429:
                    wait_seconds = self._compute_wait_seconds(resp)
                    time.sleep(wait_seconds)
                    continue

                resp.raise_for_status()
                data = resp.json()
                return MessageResponse(**data)
            except requests.RequestException as e:
                # 对于网络错误保留与之前一致的行为
                last_error = e
                break
            except ValidationError as ve:
                # 返回体格式错误不重试
                last_error = ve
                break

        if last_error is not None:
            if isinstance(last_error, ValidationError):
                raise RuntimeError(f"Invalid GPT-Proxy response format: {last_error}")
            raise RuntimeError(f"GPT request failed: {last_error}")

        # 多次 429 后仍未成功
        raise RuntimeError("GPT request rate limited (429) after retries; please try again later.")

    def _compute_wait_seconds(self, resp: requests.Response) -> float:
        """
        计算 429 后的等待秒数：
        1) 优先使用 Retry-After（秒或 HTTP 日期）
        2) 其次使用常见的 reset 头（epoch 秒）
        3) 否则对齐到下一分钟（TPM 刷新）并加少量抖动
        """
        headers = resp.headers or {}

        # 1) Retry-After
        retry_after = headers.get("Retry-After")
        if retry_after:
            try:
                seconds = float(retry_after)
                return max(0.5, min(seconds + random.uniform(0.5, 1.5), 120.0))
            except ValueError:
                try:
                    dt = parsedate_to_datetime(retry_after)
                    if dt is not None:
                        if dt.tzinfo is None:
                            dt = dt.replace(tzinfo=timezone.utc)
                        now = datetime.now(timezone.utc)
                        delta = (dt - now).total_seconds()
                        return max(0.5, min(delta + random.uniform(0.5, 1.5), 120.0))
                except Exception:
                    pass

        # 2) 常见 reset 头
        for key in ("X-RateLimit-Reset", "x-ratelimit-reset", "x-ratelimit-reset-requests", "x-ratelimit-reset-tokens"):
            if key in headers:
                try:
                    reset_epoch = float(headers[key])
                    now_epoch = utc_timestamp()  # UTC时间戳
                    delta = reset_epoch - now_epoch
                    if delta > 0:
                        return max(0.5, min(delta + random.uniform(0.5, 1.5), 120.0))
                except ValueError:
                    continue

        # 3) 对齐到下一分钟（TPM 刷新）
        now = utc_timestamp()  # UTC时间戳
        seconds_to_next_minute = 60.0 - (now % 60.0)
        # 保守一些，加上少量抖动
        return max(1.0, min(seconds_to_next_minute + random.uniform(0.5, 1.5), 70.0))
