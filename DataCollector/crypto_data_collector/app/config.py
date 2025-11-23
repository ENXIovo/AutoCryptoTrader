from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    
    BINANCE_API_URL: str = Field(default="https://data-api.binance.vision/api/v3", env="BINANCE_API_URL")
    KRAKEN_API_URL: str = Field(default="https://api.kraken.com/0/public", env="KRAKEN_API_URL")
    DATABASE_URL: str = Field(..., env="DATABASE_URL")
    CELERY_BROKER_URL: str = Field(default="redis://redis-server:6379/0", env="CELERY_BROKER_URL")
    CELERY_RESULT_BACKEND: str = Field(default="redis://redis-server:6379/0", env="CELERY_RESULT_BACKEND")

    SYMBOLS: list[str] = Field(default_factory=list, env="SYMBOLS")

    # M2 DataStore 配置
    DATA_STORE_PATH: str = Field(default="/app/data", env="DATA_STORE_PATH")

settings = Settings()
