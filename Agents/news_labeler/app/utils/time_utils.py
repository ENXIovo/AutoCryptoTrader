from __future__ import annotations

from datetime import datetime
from typing import Optional


def parse_ts(ts: str) -> Optional[datetime]:
    """宽松解析 ISO8601，支持末尾 Z。返回 naive/aware 由输入决定。"""
    if not ts:
        return None
    try:
        if ts.endswith("Z"):
            ts = ts[:-1] + "+00:00"
        return datetime.fromisoformat(ts)
    except Exception:
        return None


def period_to_window_hours(period: Optional[str]) -> Optional[int]:
    """day|week|month -> 小时数；None 则不限制窗口。"""
    if not period:
        return None
    p = period.lower()
    if p == "day":
        return 24
    if p == "week":
        return 7 * 24
    if p == "month":
        return 30 * 24
    return None
