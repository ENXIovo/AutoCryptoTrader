"""
Time utilities - UTC时间工具函数
统一所有时间处理为UTC时区
"""
from datetime import datetime, timezone
from typing import Optional


def utc_now() -> datetime:
    """
    获取当前UTC时间（aware datetime）
    
    Returns:
        UTC aware datetime对象
    """
    return datetime.now(timezone.utc)


def utc_timestamp() -> float:
    """
    获取当前UTC时间戳（Unix timestamp）
    
    Returns:
        UTC时间戳（float）
    """
    return datetime.now(timezone.utc).timestamp()


def ensure_utc(dt: datetime) -> datetime:
    """
    确保datetime对象是UTC aware
    
    Args:
        dt: datetime对象（可能没有时区信息）
        
    Returns:
        UTC aware datetime对象
    """
    if dt.tzinfo is None:
        # 如果没有时区信息，假设是UTC
        return dt.replace(tzinfo=timezone.utc)
    elif dt.tzinfo != timezone.utc:
        # 如果有其他时区，转换为UTC
        return dt.astimezone(timezone.utc)
    return dt


def parse_utc_datetime(ts: str) -> Optional[datetime]:
    """
    解析时间戳字符串为UTC aware datetime
    支持Unix时间戳（字符串或数字）和ISO8601格式
    
    Args:
        ts: 时间戳字符串
        
    Returns:
        UTC aware datetime对象，如果解析失败则返回None
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
        
        # 尝试解析为ISO8601
        if ts.endswith("Z"):
            ts = ts[:-1] + "+00:00"
        dt = datetime.fromisoformat(ts)
        return ensure_utc(dt)
    except Exception:
        return None

