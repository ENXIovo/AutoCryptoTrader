from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import List, Optional

from ..config import settings
from ..utils.redis_utils import new_redis
from ..models import NewsItem
from ..tasks import recompute_scores
from ..utils.time_utils import parse_ts, period_to_window_hours

logger = logging.getLogger(__name__)


def get_top_news(limit: int, period: Optional[str], refresh: bool) -> List[NewsItem]:
    """
    查询 Top 新闻：
      - period: day|week|month -> 只取该时间窗内的数据
      - refresh: 返回前先重算分数并做一次懒清理
    """
    r = new_redis()
    window_hours = period_to_window_hours(period)

    if refresh:
        # 仅对窗口内的数据做增量重算，提升效率
        recompute_scores(window_hours=window_hours)

    zkey = settings.redis_zset_key
    hprefix = settings.redis_hash_prefix

    members = r.zrevrange(zkey, 0, -1, withscores=True)

    now = datetime.now(timezone.utc)
    threshold = None
    if window_hours is not None:
        threshold = now - timedelta(hours=window_hours)

    results: List[NewsItem] = []
    for raw_member, score in members:
        key = raw_member.decode() if hasattr(raw_member, "decode") else str(raw_member)
        hkey = f"{hprefix}{key}"

        data = r.hgetall(hkey)
        if not data:
            # 懒清理：zset 残留的成员
            r.zrem(zkey, key)
            continue

        def _d(k: bytes) -> str:
            v = data.get(k)
            return v.decode() if hasattr(v, "decode") else (v or "")

        ts = _d(b"ts")
        dt = parse_ts(ts)
        if threshold and dt and dt.replace(tzinfo=timezone.utc) < threshold:
            continue

        results.append(NewsItem(
            source=_d(b"source"),
            category=_d(b"category"),
            importance=_d(b"importance"),
            durability=_d(b"durability"),
            summary=_d(b"summary"),
            confidence=_d(b"confidence"),
            ts=ts,
            key=key,
            label_version=_d(b"label_version"),
            weight=float(score),
        ))
        if len(results) >= limit:
            break

    return results
