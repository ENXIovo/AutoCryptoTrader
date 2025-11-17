from pydantic import Field
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    KRAKEN_API_KEY: str = Field(..., env="KRAKEN_API_KEY")
    KRAKEN_API_SECRET: str = Field(..., env="KRAKEN_API_SECRET")
    KRAKEN_API_URL: str = Field(default="https://api.kraken.com", env="KRAKEN_API_URL")
    REDIS_URL: str = Field(..., env="REDIS_URL")
    # DataCollector service for last_price snapshots
    DATA_SERVICE_URL: str = Field(..., env="DATA_SERVICE_URL")

    # WebSocket 配置
    WS_ENABLED: bool = Field(default=True, env="WS_ENABLED")
    KRAKEN_WS_AUTH_URL: str = Field(default="wss://ws-auth.kraken.com/v2", env="KRAKEN_WS_AUTH_URL")
    WS_RECONNECT_BACKOFF_SEC: int = Field(default=5, env="WS_RECONNECT_BACKOFF_SEC")
    KRAKEN_WS_TOKEN_TTL_SEC: int = Field(default=14 * 60, env="KRAKEN_WS_TOKEN_TTL_SEC")  # 提前于官方过期刷新

    # 外部变更策略
    EXTERNAL_SL_CANCEL_POLICY: str = Field(default="close", env="EXTERNAL_SL_CANCEL_POLICY")  # close | replace
    FOREIGN_ORDER_POLICY: str = Field(default="alert", env="FOREIGN_ORDER_POLICY")  # ignore | alert | close_trade

    # Redis Streams
    REDIS_STREAM_KEY: str = Field(default="trading:actions", env="REDIS_STREAM_KEY")
    REDIS_STREAM_GROUP: str = Field(default="trading-executors", env="REDIS_STREAM_GROUP")
    REDIS_STREAM_CONSUMER: str = Field(default="executor-1", env="REDIS_STREAM_CONSUMER")
    STREAM_READ_BLOCK_MS: int = Field(default=5000, env="STREAM_READ_BLOCK_MS")
    STREAM_READ_COUNT: int = Field(default=1, env="STREAM_READ_COUNT")
    STREAM_PENDING_MIN_IDLE_MS: int = Field(default=5 * 60 * 1000, env="STREAM_PENDING_MIN_IDLE_MS")
    STREAM_PENDING_CLAIM_BATCH: int = Field(default=100, env="STREAM_PENDING_CLAIM_BATCH")

    ORDER_EVENT_TTL_SEC: int = Field(default=24 * 3600, env="ORDER_EVENT_TTL_SEC")
    ORDER_AUDIT_STREAM_KEY: str = Field(default="kraken:audit", env="ORDER_AUDIT_STREAM_KEY")
    ORDER_EVENT_STREAM_PREFIX: str = Field(default="kraken:orders:", env="ORDER_EVENT_STREAM_PREFIX")

    # 锁配置
    LOCK_KEY_PREFIX: str = Field(default="lock:userref:", env="LOCK_KEY_PREFIX")
    LOCK_TTL_SEC: int = Field(default=30, env="LOCK_TTL_SEC")
    LOCK_RETRY_SLEEP_SEC: float = Field(default=0.05, env="LOCK_RETRY_SLEEP_SEC")

    # 等待/超时配置
    ORDER_WAIT_BLOCK_MS: int = Field(default=500, env="ORDER_WAIT_BLOCK_MS")
    ORDER_WAIT_POLL_SLEEP_SEC: float = Field(default=0.1, env="ORDER_WAIT_POLL_SLEEP_SEC")
    ORDER_CLOSED_TIMEOUT_SEC: int = Field(default=60, env="ORDER_CLOSED_TIMEOUT_SEC")
    ORDER_AMEND_TIMEOUT_SEC: int = Field(default=30, env="ORDER_AMEND_TIMEOUT_SEC")
    ORDER_CANCEL_TIMEOUT_SEC: int = Field(default=30, env="ORDER_CANCEL_TIMEOUT_SEC")

    # 监控间隔
    MONITOR_TICKER_INTERVAL_SEC: float = Field(default=1.0, env="MONITOR_TICKER_INTERVAL_SEC")
    MONITOR_ERROR_RETRY_SEC: float = Field(default=10.0, env="MONITOR_ERROR_RETRY_SEC")

    # 业务规则：最小止盈名义金额（USD）
    TP_MIN_NOTIONAL_USD: float = Field(default=10.0, env="TP_MIN_NOTIONAL_USD")

    # Kraken AssetPairs 缓存
    KRAKEN_PAIRS_CACHE_TTL_SEC: int = Field(default=3600, env="KRAKEN_PAIRS_CACHE_TTL_SEC")
    KRAKEN_PAIRS_REDIS_KEY: str = Field(default="kraken:assetpairs:cache:v1", env="KRAKEN_PAIRS_REDIS_KEY")

    # Redis 连接/退避
    REDIS_HEALTHCHECK_INTERVAL: int = Field(default=30, env="REDIS_HEALTHCHECK_INTERVAL")
    REDIS_SOCKET_CONNECT_TIMEOUT: int = Field(default=5, env="REDIS_SOCKET_CONNECT_TIMEOUT")
    REDIS_SOCKET_TIMEOUT: int = Field(default=10, env="REDIS_SOCKET_TIMEOUT")
    REDIS_BACKOFF_BASE: float = Field(default=0.2, env="REDIS_BACKOFF_BASE")
    REDIS_BACKOFF_FACTOR: float = Field(default=1.5, env="REDIS_BACKOFF_FACTOR")
    REDIS_RETRY_MAX_SECONDS: float = Field(default=10.0, env="REDIS_RETRY_MAX_SECONDS")
    
    class Config:
        env_file = ".env"
        extra = "ignore"

settings = Settings()