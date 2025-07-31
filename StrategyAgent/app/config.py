from pydantic import Field
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    # GPT-Proxy 的 HTTP 地址
    gpt_proxy_url: str = Field(..., env="GPT_PROXY_URL")
    # CryptoNewsCollector 服务地址
    news_service_url: str = Field(..., env="NEWS_SERVICE_URL")
    # 可以继续增加：order_service_url, wallet_service_url, api_key_xyz, ...

    class Config:
        env_file = ".env"          # 支持从 .env 文件读取
        env_file_encoding = "utf-8"

# 单例 settings 对象，全项目 import 这一份
settings = Settings()
