"""
Configuration management - 单职责：只负责配置管理
"""
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # Hyperliquid 配置
    HYPERLIQUID_ACCOUNT_ADDRESS: str = Field(
        ..., 
        env="HYPERLIQUID_ACCOUNT_ADDRESS",
        description="Hyperliquid account address (public key)"
    )
    HYPERLIQUID_SECRET_KEY: str = Field(
        ..., 
        env="HYPERLIQUID_SECRET_KEY",
        description="Hyperliquid private key (0x...)"
    )
    HYPERLIQUID_TESTNET: bool = Field(
        default=False, 
        env="HYPERLIQUID_TESTNET",
        description="Use testnet API if True"
    )


settings = Settings()
