from pydantic import Field
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    KRAKEN_API_KEY: str = Field(..., env="KRAKEN_API_KEY")
    KRAKEN_API_SECRET: str = Field(..., env="KRAKEN_API_SECRET")
    KRAKEN_API_URL: str = Field(default="https://api.kraken.com", env="KRAKEN_API_URL")
    REDIS_URL_LEDGER = Field(..., env="REDIS_URL_LEDGER")
    CELERY_BROKER_URL = Field(..., env="CELERY_BROKER_URL")
    CELERY_RESULT_BACKEND = Field(..., env="CELERY_RESULT_BACKEND")
    
    class Config:
        env_file = ".env"
        extra = "ignore"

settings = Settings()