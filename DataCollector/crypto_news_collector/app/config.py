from pydantic_settings import BaseSettings
from pydantic import Field

class Settings(BaseSettings):
    # Telegram credentials
    TELEGRAM_API_ID: int = Field(..., env="TELEGRAM_API_ID")
    TELEGRAM_API_HASH: str = Field(..., env="TELEGRAM_API_HASH")
    TELEGRAM_SESSION: str = Field("news_session", env="TELEGRAM_SESSION")
    TELEGRAM_CHANNELS: str = Field("", env="TELEGRAM_CHANNELS")  # comma-separated channel usernames/IDs

    # Redis connection（简化命名：去掉类型前缀）
    REDIS_URL: str = Field("redis://redis-server:6379/0", env="REDIS_URL")
    REDIS_STREAM_KEY: str = Field("news:raw", env="REDIS_STREAM_KEY")
    REDIS_STREAM_MAXLEN: int = Field(10000, env="REDIS_STREAM_MAXLEN")  # max length for stream; older entries trimmed
    
    # News Labeler Redis keys (用于读取已标注的新闻)
    NEWS_HASH_PREFIX: str = Field("news:", env="NEWS_HASH_PREFIX")
    NEWS_ZSET_KEY: str = Field("news:top", env="NEWS_ZSET_KEY")
    
    # M2 DataStore 配置
    DATA_STORE_PATH: str = Field(default="/app/data", env="DATA_STORE_PATH")
    
    # Celery配置
    CELERY_BROKER_URL: str = Field(default="redis://redis-server:6379/0", env="CELERY_BROKER_URL")
    CELERY_RESULT_BACKEND: str = Field(default="redis://redis-server:6379/0", env="CELERY_RESULT_BACKEND")

    class Config:
        env_file = ".env"

settings = Settings()
