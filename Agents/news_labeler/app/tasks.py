import logging
from redis import Redis
from .config import settings
from .redis_utils import compute_weight, new_redis, parse_iso_ts
from datetime import datetime, timezone, timedelta


logger = logging.getLogger(__name__)


def recompute_weights(window_hours: int | None = None) -> int:
    """
    简化版：全量遍历 zset 成员并重算分数。
    如果你要“只重算最近 N 小时”，可以在 hash 里加 last_updated 并做筛选。
    """
    r: Redis = new_redis()
    zkey = settings.redis_zset_key
    hprefix = settings.redis_hash_prefix

    cutoff = None
    if window_hours is not None and window_hours > 0:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=window_hours)

    total = 0
    members = r.zrange(zkey, 0, -1)
    for m in members:
        key = m.decode()
        hkey = f"{hprefix}{key}"
        ts = r.hget(hkey, "ts")
        imp = r.hget(hkey, "importance")
        dur = r.hget(hkey, "durability")
        if not (ts and imp and dur):
            continue

        try:
            ts_dt = parse_iso_ts(ts.decode())
            if cutoff and ts_dt < cutoff:
                continue

            weight = compute_weight(float(imp), dur.decode(), ts.decode())
            r.zadd(zkey, {key: weight})
            r.hset(hkey, "weight", str(weight))
            total += 1
        except Exception:
            logger.exception("recompute failed for key=%s", key)

    return total