from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Dict, Optional

from .config import settings
from .utils.redis_utils import new_redis, compute_weight
from .utils.time_utils import parse_ts  # ✅ 复用公共工具

logger = logging.getLogger(__name__)


def _norm(x: str) -> str:
    return re.sub(r"\W+", "", (x or "").strip().lower())


def _source_factor(source: str) -> float:
    s = _norm(source)
    for k, v in settings.source_factor_map.items():
        if _norm(k) == s:
            return float(v)
    return 0.8


def _category_factor(categories) -> float:
    if not categories:
        return 1.0
    if isinstance(categories, str):
        cats = [c.strip().lower() for c in categories.split(",") if c.strip()]
    else:
        cats = [str(c).strip().lower() for c in categories if str(c).strip()]
    if not cats:
        return 1.0
    factors = [float(settings.category_factor_map.get(c, 1.0)) for c in cats]
    up = max([f for f in factors if f >= 1.0], default=1.0)
    down = min([f for f in factors if f < 1.0], default=1.0)
    return up * down


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
        source = _d(b"source") or ""
        category_s = _d(b"category") or ""
        label_version = (_d(b"label_version") or "").lower()

        base = compute_weight(importance, durability, ts)
        mult_src = _source_factor(source)

        cats = [c.strip() for c in category_s.split(",") if c.strip()]
        is_whale_like = ("whale_transaction" in [c.lower() for c in cats]) or label_version.startswith("whale")
        if not settings.apply_category_for_whale and is_whale_like:
            mult_cat = 1.0
        else:
            mult_cat = _category_factor(cats)

        final = base * mult_src * mult_cat
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
