from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field
from typing import Dict, List


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # OpenAI / Structured Outputs
    openai_api_key: str = Field(..., env="OPENAI_API_KEY")
    labeler_model: str = Field("gpt-5-mini", env="LABELER_MODEL")
    labeler_system_prompt: str = Field(
        """
You are a strict, no-hallucination crypto news labeler.

- category: choose 1–3 from the controlled list.
- importance (0–1):
  * 0.9-1.0: CRITICAL. Federal Reserve rates, SEC Regulation, Exchange Insolvency, Protocol Hacks > $100M.
  * 0.7-0.8: MAJOR. Large price moves (>10%), Mainnet upgrades, Institutional adoption.
  * 0.5-0.6: NOTABLE. Routine volatility explanation, minor partnerships.
  * < 0.5: NOISE. Gossip, small token pumps.
  
  Do NOT give > 0.8 for routine market reports or opinion pieces unless they contain breaking regulatory/macro news.

- durability: hours=6h; days=7d; weeks=3w; months=3mo.
- confidence (0–1): 0.3=speculative; 0.9=explicit proof.
- summary: one neutral English sentence.
""",
        env="LABELER_SYSTEM_PROMPT"
    )


    # Redis 基础（简化命名：去掉类型前缀）
    redis_url: str = Field("redis://redis-server:6379/0", env="REDIS_URL")
    redis_stream_key: str = Field("news:raw", env="REDIS_STREAM_KEY")
    redis_hash_prefix: str = Field("news:", env="REDIS_HASH_PREFIX")
    redis_zset_key: str = Field("news:top", env="REDIS_ZSET_KEY")

    # 消费者组
    stream_consumer_group: str = Field("news_labeler", env="STREAM_CONSUMER_GROUP")
    stream_batch_size: int = Field(50, env="STREAM_BATCH_SIZE")
    stream_block_ms: int = Field(5000, env="STREAM_BLOCK_MS")  # 阻塞读取时长

    # 半衰期（小时）
    half_life_hours: Dict[str, float] = Field(
        {"hours": 3, "days": 48, "weeks": 168, "months": 720},
        env="HALF_LIFE_HOURS",
    )

    # TTL 映射（秒）
    durability_ttl_seconds: Dict[str, int] = Field(
        {
            "hours": 6 * 3600,
            "days": 7 * 24 * 3600,
            "weeks": 21 * 24 * 3600,
            "months": 90 * 24 * 3600,
        },
        env="DURABILITY_TTL_SECONDS",
    )

    # Redis 连接与重试
    redis_healthcheck_interval: int = Field(30, env="REDIS_HEALTHCHECK_INTERVAL")
    redis_socket_connect_timeout: int = Field(5, env="REDIS_SOCKET_CONNECT_TIMEOUT")
    redis_socket_timeout: int = Field(10, env="REDIS_SOCKET_TIMEOUT")

    # 重试/退避
    redis_retry_max_seconds: int = Field(60, env="REDIS_RETRY_MAX_SECONDS")
    redis_backoff_base: float = Field(0.5, env="REDIS_BACKOFF_BASE")
    redis_backoff_factor: float = Field(2.0, env="REDIS_BACKOFF_FACTOR")

    # Whale 来源（逗号分隔或 JSON 数组）
    whale_sources: List[str] = Field(default_factory=lambda: ["whale_alert_io"], env="WHALE_SOURCES")

    # 只这几个频道（逗号分隔即可）：WatcherGuru, BitcoinMagazineTelegram, cointelegraph, whale_alert_io, CoinDeskGlobal, cryptoslatenews
    telegram_channels: List[str] = Field(default_factory=list, env="TELEGRAM_CHANNELS")

    def model_post_init(self, __context) -> None:
        # 统一 telegram_channels：支持逗号串
        if isinstance(self.telegram_channels, str):
            self.telegram_channels = [x.strip() for x in self.telegram_channels.split(",") if x.strip()]

        # whale_sources：容错逗号串/大小写
        self.whale_sources = [s.strip() for s in self.whale_sources] if isinstance(self.whale_sources, list) else [
            x.strip() for x in str(self.whale_sources).split(",") if x.strip()
        ]
        
settings = Settings()
