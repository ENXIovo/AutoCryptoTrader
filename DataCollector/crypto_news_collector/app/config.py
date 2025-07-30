from pydantic import Field
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    DATABASE_URL: str = Field(..., env="DATABASE_URL")
    TELEGRAM_API_ID: int = Field(..., env="TELEGRAM_API_ID")
    TELEGRAM_API_HASH: str = Field(..., env="TELEGRAM_API_HASH")
    TELEGRAM_SESSION: str = Field("news_session", env="TELEGRAM_SESSION")
    TELEGRAM_CHANNELS: str = Field("WatcherGuru,wublockgroup", env="TELEGRAM_CHANNELS")
    TELEGRAM_BOT_TOKEN: str = Field(..., env="TELEGRAM_BOT_TOKEN")

    class Config:
        env_file = ".env"  # 保留支持 .env 文件的功能
        extra = "ignore"

settings = Settings()
