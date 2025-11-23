from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, Optional

from .config import settings
from .utils.redis_utils import new_redis, compute_weight
from .utils.time_utils import parse_ts  # ✅ 复用公共工具

logger = logging.getLogger(__name__)


def recompute_scores(window_hours: Optional[int] = None) -> Dict[str, int]:
    """
    重算现有新闻的权重；同时对找不到 hash 的 zset 成员做懒清理。
    window_hours: 仅重算最近 N 小时数据（None=全量）。
    """
    r = new_redis()
    zkey = settings.redis_zset_key
    hprefix = settings.redis_hash_prefix

    members = r.zrange(zkey, 0, -1)
    now = datetime.now(timezone.utc)
    threshold = None
    if window_hours is not None:
        threshold = now - timedelta(hours=window_hours)

    scanned = 0
    recomputed = 0
    removed = 0

    for raw_member in members:
        member = raw_member.decode() if hasattr(raw_member, "decode") else str(raw_member)
        scanned += 1
        hkey = f"{hprefix}{member}"

        data = r.hgetall(hkey)
        if not data:
            r.zrem(zkey, member)
            removed += 1
            continue

        def _d(k: bytes) -> str:
            v = data.get(k)
            return v.decode() if hasattr(v, "decode") else (v or "")

        ts = _d(b"ts")
        dt = parse_ts(ts)
        if threshold and dt and dt.replace(tzinfo=timezone.utc) < threshold:
            continue

        try:
            importance = float(_d(b"importance") or 0.0)
        except Exception:
            importance = 0.0
        durability = _d(b"durability") or "days"

        # 只使用 GPT 的 importance + 时间衰减，不再应用 source/category 因子
        final = compute_weight(importance, durability, ts)
        r.zadd(zkey, {member: final})
        try:
            r.hset(hkey, mapping={"weight": str(final)})
        except Exception:
            pass

        recomputed += 1

    logger.info(
        "[tasks.recompute] scanned=%d recomputed=%d removed=%d window_hours=%s",
        scanned, recomputed, removed, window_hours
    )
    return {"scanned": scanned, "recomputed": recomputed, "removed": removed}
