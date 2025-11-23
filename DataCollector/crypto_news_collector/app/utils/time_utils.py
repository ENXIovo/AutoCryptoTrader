"""
Time utilities - 时间工具函数
"""
from datetime import datetime, timezone
from typing import Optional


def parse_ts(ts: str) -> Optional[datetime]:
    """
    解析时间戳：支持Unix时间戳（字符串或数字）和ISO8601格式
    返回 UTC aware datetime
    """
    if not ts:
        return None
    try:
        # 尝试解析为Unix时间戳（字符串或数字）
        try:
            timestamp = float(ts)
            return datetime.fromtimestamp(timestamp, tz=timezone.utc)
        except (ValueError, TypeError):
            pass
        
        # 尝试解析为ISO8601（向后兼容）
        if ts.endswith("Z"):
            ts = ts[:-1] + "+00:00"
        dt = datetime.fromisoformat(ts)
        # 确保返回UTC aware
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None

