import time
import logging
from typing import Dict, Iterable, Tuple

from redis import Redis
from redis.exceptions import ConnectionError, TimeoutError as RedisTimeout

from app.config import settings


logger = logging.getLogger(__name__)


def new_redis() -> Redis:
    # 与 news_labeler 一致的封装；此处简化，仅开启 decode_responses 以返回 str
    return Redis.from_url(
        settings.REDIS_URL,
        decode_responses=True,
        health_check_interval=settings.REDIS_HEALTHCHECK_INTERVAL,
        socket_connect_timeout=settings.REDIS_SOCKET_CONNECT_TIMEOUT,
        socket_timeout=settings.REDIS_SOCKET_TIMEOUT,
    )


def _sleep_backoff(attempt: int) -> None:
    # 退避：0.2 * 1.5^n，上限 10 秒
    delay = settings.REDIS_BACKOFF_BASE * (settings.REDIS_BACKOFF_FACTOR ** attempt)
    delay = min(delay, settings.REDIS_RETRY_MAX_SECONDS)
    time.sleep(delay)


def safe_call(func, *args, **kwargs):
    exc: Exception | None = None
    for attempt in range(0, 32):
        try:
            return func(*args, **kwargs)
        except (ConnectionError, RedisTimeout) as e:
            exc = e
            logger.warning("Redis op failed (attempt=%s): %s", attempt + 1, e)
            _sleep_backoff(attempt)
        except Exception:
            raise
    raise exc if exc else RuntimeError("unknown redis error")


def ensure_group(r: Redis) -> None:
    def _create():
        try:
            # 与 news_labeler 一致：从最新（$）开始
            r.xgroup_create(settings.REDIS_STREAM_KEY, settings.REDIS_STREAM_GROUP, id="$", mkstream=True)
        except Exception:
            pass
    safe_call(_create)


def xreadgroup(r: Redis, group: str, consumer: str, count: int, block_ms: int):
    def _read():
        return r.xreadgroup(group, consumer, {settings.REDIS_STREAM_KEY: ">"}, count=count, block=block_ms)
    return safe_call(_read)


def xack(r: Redis, group: str, msg_id: str) -> None:
    def _ack():
        r.xack(settings.REDIS_STREAM_KEY, group, msg_id)
    safe_call(_ack)


def xread_block(r: Redis, key: str, last_id: str, block_ms: int, count: int = 1):
    """封装 XREAD（阻塞）。与 news_labeler 风格一致，统一重试语义。"""
    def _read():
        return r.xread({key: last_id}, block=block_ms, count=count)
    return safe_call(_read)


def xautoclaim_stale(
    r: Redis,
    group: str,
    consumer: str,
    min_idle_ms: int,
    batch: int,
) -> Iterable[Tuple[str, Dict[str, str]]]:
    last_id: str = "0-0"
    while True:
        def _claim():
            return r.xautoclaim(
                name=settings.REDIS_STREAM_KEY,
                groupname=group,
                consumername=consumer,
                min_idle_time=min_idle_ms,
                start_id=last_id,
                count=batch,
                justid=False,
            )

        result = safe_call(_claim)

        if not isinstance(result, (list, tuple)):
            break
        if len(result) == 2:
            next_id, messages = result
        elif len(result) == 3:
            next_id, messages, _deleted = result
        else:
            break

        if not messages:
            break

        for mid, fields in messages:
            yield str(mid), {str(k): str(v) for k, v in (fields or {}).items()}

        last_id = str(next_id)


