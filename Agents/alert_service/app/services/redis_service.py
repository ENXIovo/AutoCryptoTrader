import time
import logging
import redis
from typing import List, Tuple, Dict, Optional
from ..config import settings

logger = logging.getLogger(__name__)

class RedisService:
    def __init__(self):
        self.client = redis.Redis.from_url(settings.REDIS_URL, decode_responses=True)

    def get_high_score_items(self, min_score: float) -> List[Tuple[str, float]]:
        """
        Retrieve items from ZSET with score >= min_score.
        Returns list of (key, score).
        """
        return self.client.zrangebyscore(
            settings.REDIS_ZSET_KEY, 
            min_score, 
            "+inf", 
            withscores=True
        )

    def is_alert_sent(self, key: str) -> bool:
        """Check if an alert for this key has already been sent."""
        return self.client.sismember(settings.REDIS_SENT_KEY, key)

    def mark_alert_as_sent(self, key: str, ttl: int = 604800):
        """Mark an alert as sent and set expiry (default 7 days)."""
        self.client.sadd(settings.REDIS_SENT_KEY, key)
        self.client.expire(settings.REDIS_SENT_KEY, ttl)

    def get_news_details(self, key: str) -> Optional[Dict[str, str]]:
        """Fetch news details from Hash."""
        hash_key = f"{settings.REDIS_HASH_PREFIX}{key}"
        data = self.client.hgetall(hash_key)
        return data if data else None

    def add_to_history(self, key: str, score: float, summary: str):
        """Add alert record to history list for observability."""
        history_entry = f"{time.strftime('%Y-%m-%d %H:%M:%S')} | {key} | {score:.2f} | {summary}"
        self.client.lpush(settings.REDIS_HISTORY_KEY, history_entry)
        self.client.ltrim(settings.REDIS_HISTORY_KEY, 0, 99)  # Keep last 100 alerts

