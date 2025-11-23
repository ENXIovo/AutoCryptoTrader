"""
Celery Tasks - 单职责：定期归档News数据到Parquet
从Redis读取已标注的新闻，按日期写入Parquet文件
"""
import logging
from datetime import datetime, date, timedelta, timezone
from collections import defaultdict
from typing import Dict, Any

from celery import Celery
from celery.schedules import crontab
import redis

from .config import settings
from .data_writer import news_data_writer
from .utils.time_utils import parse_ts

logger = logging.getLogger(__name__)

# 初始化Celery
celery_app = Celery(
    "news_tasks",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND,
)

# 配置队列名称，避免与其他Celery app冲突
celery_app.conf.task_default_queue = "news_collector"
celery_app.conf.task_routes = {
    "app.tasks.*": {"queue": "news_collector"},
}

celery_app.conf.beat_schedule = {
    "archive-news-daily": {
        "task": "app.tasks.archive_news_to_parquet",
        "schedule": crontab(hour=1, minute=0),  # 每天凌晨1点归档昨天的数据
    },
}
celery_app.conf.timezone = "UTC"


def _decode(v: bytes | None) -> str:
    """解码Redis返回的bytes"""
    return v.decode() if isinstance(v, (bytes, bytearray)) else (v or "")


@celery_app.task
def archive_news_to_parquet():
    """
    定期归档News数据到Parquet
    从Redis读取已标注的新闻，按日期写入Parquet文件
    
    策略：
    - 归档昨天的数据（避免写入未完成的当天数据）
    - 从Redis Hash读取已标注的新闻
    - 按日期分组并写入Parquet
    """
    try:
        # 连接Redis
        r = redis.Redis.from_url(settings.REDIS_URL, decode_responses=False)
        
        # 获取昨天的日期（避免写入未完成的当天数据）
        target_date = date.today() - timedelta(days=1)
        start_ts = datetime.combine(target_date, datetime.min.time()).replace(tzinfo=timezone.utc).timestamp()
        end_ts = datetime.combine(target_date, datetime.max.time()).replace(tzinfo=timezone.utc).timestamp()
        
        logger.info(f"[ArchiveNews] Starting archive for {target_date} (ts: {start_ts} to {end_ts})")
        
        # 从Redis ZSet获取所有news keys
        zkey = settings.NEWS_ZSET_KEY
        hprefix = settings.NEWS_HASH_PREFIX
        
        members = r.zrange(zkey, 0, -1)
        logger.info(f"[ArchiveNews] Found {len(members)} news items in Redis")
        
        # 按日期分组收集news数据
        news_by_date = defaultdict(list)
        processed = 0
        skipped = 0
        
        for raw_member in members:
            key = None
            try:
                key = raw_member.decode() if isinstance(raw_member, bytes) else str(raw_member)
                hkey = f"{hprefix}{key}"
                
                # 获取Hash数据
                data = r.hgetall(hkey)
                if not data:
                    skipped += 1
                    continue
                
                # 解析字段
                def _d(k: bytes) -> str:
                    v = data.get(k)
                    return v.decode() if isinstance(v, bytes) else (v or "")
                
                ts_str = _d(b"ts")
                if not ts_str:
                    skipped += 1
                    continue
                
                # 解析时间戳
                try:
                    timestamp = float(ts_str)
                except (ValueError, TypeError):
                    # 尝试解析ISO字符串
                    dt = parse_ts(ts_str)
                    if not dt:
                        skipped += 1
                        continue
                    timestamp = dt.timestamp()
                
                # 过滤目标日期范围
                if timestamp < start_ts or timestamp > end_ts:
                    continue
                
                # 构建news item（只保存已标注的信息，不包含原始text）
                news_item: Dict[str, Any] = {
                    "key": key,
                    "source": _d(b"source") or "",
                    "ts": ts_str,
                    "timestamp": timestamp,
                    "category": _d(b"category") or "",
                    "importance": _d(b"importance") or "0.0",
                    "durability": _d(b"durability") or "days",
                    "summary": _d(b"summary") or "",
                    "confidence": _d(b"confidence") or "0.0",
                    "label_version": _d(b"label_version") or "unknown",
                    "weight": float(_d(b"weight") or "0.0"),
                }
                
                # 从key中提取chat_id和message_id（如果存在）
                if ":" in key:
                    parts = key.split(":", 1)
                    if len(parts) == 2:
                        news_item["chat_id"] = parts[0]
                        news_item["message_id"] = parts[1]
                
                # 按日期分组（使用UTC时区）
                item_date = datetime.fromtimestamp(timestamp, tz=timezone.utc).date()
                news_by_date[item_date].append(news_item)
                processed += 1
                
            except Exception as e:
                key_str = key if key else "unknown"
                logger.warning(f"[ArchiveNews] Error processing key {key_str}: {e}")
                skipped += 1
                continue
        
        logger.info(f"[ArchiveNews] Processed: {processed}, Skipped: {skipped}")
        
        # 获取可写日期范围（增量滚动存储）
        min_allowed_date, max_allowed_date = news_data_writer.get_writable_date_range()
        
        # 写入Parquet文件（只处理可写日期）
        written_count = 0
        skipped_dates = 0
        for item_date, items in news_by_date.items():
            # 过滤：只处理可写日期范围内的数据
            if min_allowed_date is not None and item_date < min_allowed_date:
                skipped_dates += 1
                continue
            if item_date > max_allowed_date:
                skipped_dates += 1
                continue
            
            try:
                success = news_data_writer.write_news_for_date(item_date, items)
                if success:
                    written_count += len(items)
                    logger.info(f"[ArchiveNews] Wrote {len(items)} news items for {item_date}")
            except Exception as e:
                logger.error(f"[ArchiveNews] Failed to write news for {item_date}: {e}")
        
        if skipped_dates > 0:
            logger.info(f"[ArchiveNews] Skipped {skipped_dates} historical dates (protected)")
        
        logger.info(f"[ArchiveNews] Archive completed: {written_count} items written for {len(news_by_date)} dates")
        return {"status": "ok", "written": written_count, "dates": len(news_by_date)}
        
    except Exception as e:
        logger.error(f"[ArchiveNews] Fatal error: {e}", exc_info=True)
        return {"status": "error", "message": str(e)}

