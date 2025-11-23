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

def _format_age(now: datetime, dt: datetime) -> str:
    """将 now - dt 转为 '44 min ago' / '3 weeks ago' 之类的人类可读字符串。"""
    delta = now - dt
    sec = int(delta.total_seconds())
    if sec < 45:
        return "just now"
    minutes = sec // 60
    if minutes < 60:
        return f"{minutes} min ago"
    hours = minutes // 60
    if hours < 24:
        return f"{hours} hour ago" if hours == 1 else f"{hours} hours ago"
    days = hours // 24
    if days < 7:
        return f"{days} day ago" if days == 1 else f"{days} days ago"
    # 7 天以上转为周
    weeks = days // 7
    if days < 30:
        return f"{weeks} week ago" if weeks == 1 else f"{weeks} weeks ago"
    # 30 天以上转为月（粗略按 30 天）
    months = days // 30
    if days < 365:
        return f"{months} month ago" if months == 1 else f"{months} months ago"
    years = days // 365
    return f"{years} year ago" if years == 1 else f"{years} years ago"

def get_top_news(
    limit: int, 
    period: Optional[str],
    before_timestamp: Optional[float] = None  # 回测模式：只返回该时间之前的新闻
) -> List[NewsItem]:
    """
    查询 Top 新闻：
      - period: day|week|month -> 只取该时间窗内的数据
      - before_timestamp: 回测模式，只返回该时间戳之前的新闻
      - 总是：返回前重算分数并做一次懒清理
    """
    r = new_redis()
    window_hours = period_to_window_hours(period)

    # ⬇️ 无论何时都重算（用窗口小时做增量）
    recompute_scores(window_hours=window_hours)

    zkey = settings.redis_zset_key
    hprefix = settings.redis_hash_prefix

    members = r.zrevrange(zkey, 0, -1, withscores=True)

    # 确定"现在"时间：回测模式使用before_timestamp，否则使用当前时间
    if before_timestamp:
        now = datetime.fromtimestamp(before_timestamp, tz=timezone.utc)
    else:
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
        dt = parse_ts(ts)  # 期待返回 datetime 或 None

        # 过滤窗口外和时间点之后
        dtu = None
        if dt:
            dtu = dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
            # 回测模式：只返回before_timestamp之前的新闻
            if before_timestamp and dtu.timestamp() > before_timestamp:
                continue
            # 窗口过滤
            if threshold and dtu < threshold:
                continue

        # 生成 age（人类可读）
        age_str = _format_age(now, dtu) if dtu else None

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
            age=age_str,  # ⬅️ 新增字段
        ))
        if len(results) >= limit:
            break

    return results
