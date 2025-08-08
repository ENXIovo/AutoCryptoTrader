from pydantic_settings import BaseSettings
from pydantic import Field

class Settings(BaseSettings):
    # Telegram credentials
    TELEGRAM_API_ID: int = Field(..., env="TELEGRAM_API_ID")
    TELEGRAM_API_HASH: str = Field(..., env="TELEGRAM_API_HASH")
    TELEGRAM_SESSION: str = Field("news_session", env="TELEGRAM_SESSION")
    TELEGRAM_CHANNELS: str = Field("", env="TELEGRAM_CHANNELS")  # comma-separated channel usernames/IDs

    # Redis connection
    REDIS_URL: str = Field("redis://redis-server:6379/0", env="REDIS_URL")
    REDIS_STREAM_KEY: str = Field("stream:news:raw", env="REDIS_STREAM_KEY")
    REDIS_STREAM_MAXLEN: int = Field(10000, env="REDIS_STREAM_MAXLEN")  # max length for stream; older entries trimmed

    class Config:
        env_file = ".env"

settings = Settings()
