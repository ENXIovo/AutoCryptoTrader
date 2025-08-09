from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field
from typing import Dict, List

# ---- 默认倍率（全部小写键）----
DEFAULT_SOURCE_FACTOR_MAP: Dict[str, float] = {
    "coindeskglobal":          0.95,
    "cryptoslatenews":         0.80,
    "cointelegraph":           0.70,
    "watcherguru":             0.60,
    "bitcoinmagazinetelegram": 0.45,
    "whale_alert_io":          0.90,
}

DEFAULT_CATEGORY_FACTOR_MAP = {
    # 宏观/监管/ETF —— 能改预期、改资金通道
    "regulation":       1.35,  # 行业或国家级监管/执法/豁免/许可
    "macro":            1.20,  # 央行/宏观政策/税制/选举等
    "etf":              1.20,  # 申报/审批/大额净流入等

    # 安全/数据/衍生品 —— 会引发次级连锁或短中期波动
    "security_incident":1.12,  # 黑客/跑路/合规下架
    "onchain_metric":   1.00,  # 需结合重要性与TTL本身去区分大小
    "derivatives":      1.00,
    "mining":           0.98,

    # 稳定币与法币出入口
    "stablecoin":       1.00,

    # 交易所/项目/合作 —— 基本面改良但对大盘影响有限
    "exchange_status":  1.03,  # 新路由/功能/合规接入，略正面
    "project_upgrade":  1.06,  # 主网/重大版本，适度
    "partnership":      1.02,

    # 噪声类
    "whale_transaction":0.60,  # 保留但显著降权
}


def _parse_kv_float(s: str) -> Dict[str, float]:
    """支持 'a=0.9,b=0.8' 或带空格/换行；键统一小写。"""
    out: Dict[str, float] = {}
    for part in s.replace("\n", ",").split(","):
        part = part.strip()
        if not part:
            continue
        if "=" not in part:
            # 允许写成 'coindeskglobal:0.95'
            if ":" in part:
                k, v = part.split(":", 1)
            else:
                continue
        else:
            k, v = part.split("=", 1)
        k = k.strip().lower()
        try:
            out[k] = float(v.strip())
        except Exception:
            pass
    return out

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # OpenAI / Structured Outputs
    openai_api_key: str = Field(..., env="OPENAI_API_KEY")
    labeler_model: str = Field("gpt-5-mini", env="LABELER_MODEL")
    labeler_system_prompt: str = Field(
        """
You are a strict, no-hallucination crypto news labeler.

- Use ONLY the given text; do not add or verify facts. Output EXACTLY the JSON schema (no extra keys).
- category: choose 1–3 from the controlled list that best fit the text.
- importance (0–1): 0.1 minor (local/small-cap only), 0.5 notable (sector/medium-cap), 0.8 major (macro policy, BTC/ETH impact, >$1B scale, major legal/regulatory events).
- durability is a FIXED TTL bucket: hours=6h; days=7d; weeks=3w; months=3mo.
Pick the bucket that best matches how long the news will remain relevant for trading or market perception.
- confidence (0–1), based ONLY on the text’s phrasing/evidence:
0.3 speculative/hedged wording; 0.6 specific stated claim (entities/numbers); 0.9 explicit proof inside the text (e.g., quoted order/filing ID or first-party announcement excerpt).
- summary: one neutral English sentence with key entities, numbers, and the direct action/effect; no hype.
""",
        env="LABELER_SYSTEM_PROMPT"
    )


    # Redis 基础
    redis_url: str = Field("redis://redis-server:6379/0", env="REDIS_URL")
    redis_stream_key: str = Field("stream:news:raw", env="REDIS_STREAM_KEY")
    redis_hash_prefix: str = Field("hash:news:label:", env="REDIS_HASH_PREFIX")
    redis_zset_key: str = Field("zset:news:top", env="REDIS_ZSET_KEY")

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

    # 来源倍率 & 分类倍率（支持 JSON 或 'a=0.9,b=0.8'）
    source_factor_map: Dict[str, float] = Field(
        default_factory=lambda: DEFAULT_SOURCE_FACTOR_MAP.copy(),
        env="SOURCE_FACTOR_MAP"
    )
    category_factor_map: Dict[str, float] = Field(
        default_factory=lambda: DEFAULT_CATEGORY_FACTOR_MAP.copy(),
        env="CATEGORY_FACTOR_MAP"
    )

    # 是否对鲸鱼也应用分类倍率（默认 False）
    apply_category_for_whale: bool = Field(False, env="APPLY_CATEGORY_FOR_WHALE")

    def model_post_init(self, __context) -> None:
        # 1) 统一 telegram_channels：支持逗号串
        if isinstance(self.telegram_channels, str):
            self.telegram_channels = [x.strip() for x in self.telegram_channels.split(",") if x.strip()]

        # 2) source_factor_map：支持 JSON 或 KV 串；统一小写键
        if isinstance(self.source_factor_map, str):
            s = self.source_factor_map.strip()
            if s.startswith("{"):
                # JSON
                try:
                    import json
                    self.source_factor_map = {k.lower(): float(v) for k, v in json.loads(s).items()}
                except Exception:
                    self.source_factor_map = DEFAULT_SOURCE_FACTOR_MAP.copy()
            else:
                self.source_factor_map = _parse_kv_float(s) or DEFAULT_SOURCE_FACTOR_MAP.copy()
        else:
            self.source_factor_map = {str(k).lower(): float(v) for k, v in self.source_factor_map.items()}

        # 3) category_factor_map：同上，统一小写键
        if isinstance(self.category_factor_map, str):
            s = self.category_factor_map.strip()
            if s.startswith("{"):
                try:
                    import json
                    self.category_factor_map = {k.lower(): float(v) for k, v in json.loads(s).items()}
                except Exception:
                    self.category_factor_map = DEFAULT_CATEGORY_FACTOR_MAP.copy()
            else:
                self.category_factor_map = _parse_kv_float(s) or DEFAULT_CATEGORY_FACTOR_MAP.copy()
        else:
            self.category_factor_map = {str(k).lower(): float(v) for k, v in self.category_factor_map.items()}

        # 4) whale_sources：容错逗号串/大小写
        self.whale_sources = [s.strip() for s in self.whale_sources] if isinstance(self.whale_sources, list) else [
            x.strip() for x in str(self.whale_sources).split(",") if x.strip()
        ]
        
settings = Settings()
