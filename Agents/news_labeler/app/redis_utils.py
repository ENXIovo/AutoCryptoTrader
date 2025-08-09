import time
import logging
from typing import Dict, Iterable, Tuple
from datetime import datetime, timezone
from redis import Redis
from redis.exceptions import ConnectionError, TimeoutError as RedisTimeout
from .config import settings

logger = logging.getLogger(__name__)


def new_redis() -> Redis:
    return Redis.from_url(
        settings.redis_url,
        health_check_interval=settings.redis_healthcheck_interval,
        socket_connect_timeout=settings.redis_socket_connect_timeout,
        socket_timeout=settings.redis_socket_timeout,
        decode_responses=False,
    )


def _sleep_backoff(attempt: int):
    delay = settings.redis_backoff_base * (settings.redis_backoff_factor ** attempt)
    delay = min(delay, settings.redis_retry_max_seconds)
    time.sleep(delay)


def safe_call(func, *args, **kwargs):
    # MVP 仍保留对连接类错误的退避（避免炸穿日志/阻塞容器）
    exc: Exception | None = None
    for attempt in range(0, 64):
        try:
            return func(*args, **kwargs)
        except (ConnectionError, RedisTimeout) as e:
            exc = e
            logger.warning("Redis op failed (attempt=%s): %s", attempt + 1, e)
            _sleep_backoff(attempt)
        except Exception:
            raise
    raise exc if exc else RuntimeError("unknown redis error")


def compute_weight(importance: float, durability: str, created_ts: str) -> float:
    # MVP：假设 ts 为 ISO8601 且含时区；异常让它抛
    created_at = datetime.fromisoformat(created_ts)
    now = datetime.now(timezone.utc)
    delta_hours = (now - created_at).total_seconds() / 3600.0
    half_life = settings.half_life_hours[durability]  # 假设合法键
    return float(importance) * (0.5 ** (delta_hours / half_life))


def _ttl_for_durability(durability: str) -> int:
    return settings.durability_ttl_seconds[durability]


def save_label_to_redis(
    r: Redis,
    key: str,
    label: Dict,
    weight: float,
) -> None:
    hash_key = f"{settings.redis_hash_prefix}{key}"

    def _write():
        r.hset(hash_key, mapping=label | {"weight": str(weight)})
        r.zadd(settings.redis_zset_key, {key: weight})
        r.expire(hash_key, _ttl_for_durability(label["durability"]))
    safe_call(_write)


def ensure_group(r: Redis):
    # 从“最新”开始消费：id="$"
    def _create():
        try:
            r.xgroup_create(settings.redis_stream_key, settings.stream_consumer_group, id="$", mkstream=True)
        except Exception:
            pass
    safe_call(_create)


def xreadgroup(r: Redis, group: str, consumer: str, count: int, block_ms: int):
    def _read():
        return r.xreadgroup(group, consumer, {settings.redis_stream_key: ">"}, count=count, block=block_ms)
    return safe_call(_read)


def xack(r: Redis, group: str, msg_id: str):
    def _ack():
        r.xack(settings.redis_stream_key, group, msg_id)
    safe_call(_ack)


def xautoclaim_stale(
    r: Redis,
    group: str,
    consumer: str,
    min_idle_ms: int,
    batch: int,
) -> Iterable[Tuple[str, Dict[bytes, bytes]]]:
    last_id: bytes = b"0-0"
    while True:
        def _claim():
            return r.xautoclaim(
                name=settings.redis_stream_key,
                groupname=group,
                consumername=consumer,
                min_idle_time=min_idle_ms,
                start_id=last_id,
                count=batch,
                justid=False,
            )
        result = safe_call(_claim)
        if isinstance(result, (list, tuple)):
            if len(result) == 2:
                next_id, messages = result
            elif len(result) == 3:
                next_id, messages, _deleted = result
            else:
                break
        else:
            break

        if not messages:
            break

        for msg_id, fields in messages:
            yield (msg_id.decode() if isinstance(msg_id, (bytes, bytearray)) else str(msg_id)), fields

        last_id = next_id if isinstance(next_id, (bytes, bytearray)) else str(next_id).encode()
