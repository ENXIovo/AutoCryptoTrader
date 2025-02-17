# kraken_service/config.py

from pydantic import Field
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    KRAKEN_API_KEY: str = Field(..., env="KRAKEN_API_KEY")
    KRAKEN_API_SECRET: str = Field(..., env="KRAKEN_API_SECRET")
    KRAKEN_API_URL: str = Field(default="https://api.kraken.com", env="KRAKEN_API_URL")

    # Celery & Redis 配置
    CELERY_BROKER_URL: str = Field(default="redis://redis-server:6379/0", env="CELERY_BROKER_URL")
    CELERY_RESULT_BACKEND: str = Field(default="redis://redis-server:6379/0", env="CELERY_RESULT_BACKEND")
    REDIS_HOST: str = Field(default="redis-server", env="REDIS_HOST")
    REDIS_PORT: int = Field(default=6379, env="REDIS_PORT")

    class Config:
        env_file = ".env"
        extra = "ignore"

settings = Settings()
