"""
Configuration management - 单职责：只负责配置管理
VirtualExchange 回测系统配置（无外部API依赖）
"""
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # 回测系统配置
    INITIAL_BALANCE: float = Field(
        default=10000.0,
        env="INITIAL_BALANCE",
        description="Initial account balance for backtesting (USD)"
    )
    
    # M2 DataStore 路径（历史K线数据存储位置）
    DATA_STORE_PATH: str = Field(
        default="/app/data",
        env="DATA_STORE_PATH",
        description="Path to M2 DataStore root directory (contains candles/ and news/ subdirectories)"
    )

    # 回测时间轴配置
    BACKTEST_TIME_SCALE: float = Field(
        default=1.0,
        env="BACKTEST_TIME_SCALE",
        description="Time acceleration factor (1.0 = real-time, 60.0 = 60x speed)"
    )
    
    # 费用配置（A1简化：统一费率）
    FEE_RATE: float = Field(
        default=0.0,
        env="FEE_RATE",
        description="Trading fee rate (0.001 = 0.1%, 0.0 = no fees)"
    )


settings = Settings()
