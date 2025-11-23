from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    REDIS_URL: str = Field("redis://redis-server:6379/0", env="REDIS_URL")
    REDIS_ZSET_KEY: str = Field("news:top", env="REDIS_ZSET_KEY")
    REDIS_HASH_PREFIX: str = Field("news:", env="REDIS_HASH_PREFIX")
    REDIS_HISTORY_KEY: str = Field("alerts:history", env="REDIS_HISTORY_KEY")
    REDIS_SENT_KEY: str = Field("alerts:sent", env="REDIS_SENT_KEY")
    ALERT_THRESHOLD: float = Field(0.7, env="ALERT_THRESHOLD")
    
    # Telegram Bot
    TELEGRAM_BOT_TOKEN: str = Field(..., env="TELEGRAM_BOT_TOKEN")
    TELEGRAM_CHAT_ID: str = Field(..., env="TELEGRAM_CHAT_ID")
    
    CHECK_INTERVAL: int = Field(30, env="CHECK_INTERVAL") # seconds

settings = Settings()

