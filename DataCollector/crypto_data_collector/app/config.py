from pydantic import Field
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    BINANCE_API_URL: str = Field(default="https://data-api.binance.vision/api/v3", env="BINANCE_API_URL")
    KRAKEN_API_URL: str = Field(default="https://api.kraken.com/0/public", env="KRAKEN_API_URL")
    DATABASE_URL: str = Field(..., env="DATABASE_URL")
    CELERY_BROKER_URL: str = Field(default="redis://redis-server:6379/0", env="CELERY_BROKER_URL")
    CELERY_RESULT_BACKEND: str = Field(default="redis://redis-server:6379/0", env="CELERY_RESULT_BACKEND")

    SYMBOLS: list[str] = Field(default_factory=list, env="SYMBOLS")

    class Config:
        env_file = ".env"  # 保留支持 .env 文件的功能
        extra = "ignore"

settings = Settings()
