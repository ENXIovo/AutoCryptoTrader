# config.py

from pydantic import Field
from pydantic_settings import BaseSettings
import json


class Settings(BaseSettings):
    # ─────────── 外部服务地址 ───────────
    gpt_proxy_url: str = Field(..., env="GPT_PROXY_URL")
    news_service_url: str = Field(..., env="NEWS_SERVICE_URL")
    kraken_service_url: str = Field(..., env="KRAKEN_SERVICE_URL")
    data_service_url: str = Field(..., env="DATA_SERVICE_URL")

    # ─────────── Celery & 调度 ───────────
    celery_broker_url: str = Field("redis://redis-server:6379/0",
                                   env="CELERY_BROKER_URL")
    celery_result_backend: str = Field("redis://redis-server:6379/0",
                                       env="CELERY_RESULT_BACKEND")
    # 默认每 4 小时执行一次
    strategy_cron: str = Field("0 */4 * * *", env="STRATEGY_CRON")

    # ─────────── 代理 & 工具配置 ───────────
    # 允许通过 JSON 字符串覆写
    agent_configs_json: str | None = Field(None, env="AGENT_CONFIGS_JSON")

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()


# ---------- 代理配置帮助函数 ----------
def _default_agent_configs() -> list[dict]:
    """
    定义会议中的专家角色、职责和能力。
    这是一个串行工作流，每个Agent的分析都建立在前者之上。
    """
    return [
        {
            "name": "Market Analyst",
            "deployment_name": "gpt-4.1-mini-2025-04-14",
            "enabled": True,
            "tools": ["getCryptoNews"], # 修正了工具名称
            "prompt": """
You are a 'Market Analyst' for a crypto trading team. Your sole responsibility is to analyze the broad market environment. Please use the provided UTC time as the reference for your analysis.

Your tasks:
1. Use the `getCryptoNews` tool to get the latest market news.
2. Summarize the key news points and identify the overall market sentiment (e.g., bullish, bearish, neutral, fearful, greedy).
3. Do NOT perform any K-line analysis or give trading advice.
4. Present your findings in a clear, concise summary. Start your report with "--- Market Analyst Report ---".
""",
        },
        {
            "name": "Lead Technical Analyst",
            "deployment_name": "o3-2025-04-16",
            "enabled": True,
            "tools": ["getKlineIndicators"], # 修正了工具名称
            "prompt": """
You are the 'Lead Technical Analyst', an expert in multi-timeframe analysis. Please use the provided UTC time as the reference for your analysis.

Your tasks:
1. Carefully review the 'Market Analyst Report' provided in the previous discussion context.
2. Use the `getKlineIndicators` tool to fetch K-line data and technical indicators for a primary symbol (e.g., BTCUSD).
3. **Synthesize the market sentiment with your technical analysis.**
4. Identify the primary trend, key support/resistance levels, and any significant chart patterns across different timeframes (4h, 1h, 15m).
5. Propose a primary trading hypothesis (e.g., "Hypothesis: Long BTCUSD if it reclaims 68000 support"). Do NOT give a final trade signal yet.
6. Start your report with "--- Lead Technical Analyst Report ---".
""",
        },
        {
            "name": "Risk Manager",
            "deployment_name": "gpt-4.1-mini-2025-04-14",
            "enabled": True,
            "tools": ["getAccountInfo"], # 修正了工具名称
            "prompt": """
You are the 'Risk Manager'. Your priority is capital preservation. You are cautious and methodical. Please use the provided UTC time as the reference for your analysis.

Your tasks:
1. Review the reports from the Market and Technical Analysts in the context.
2. Use the `getAccountInfo` tool to check our current balance, positions, and overall exposure for the target symbol.
3. Based on the proposed trading hypothesis, calculate an appropriate position size according to our risk model (e.g., max 2% of total capital at risk).
4. Define a clear, non-negotiable stop-loss level based on the technical analysis.
5. Define at least two take-profit targets (e.g., TP1 for partial profit-taking, TP2 for the final target).
6. Calculate the Risk-to-Reward Ratio (RRR). If RRR is below 2.0, you must voice strong opposition to the trade.
7. Start your report with "--- Risk Manager Report ---".
""",
        },
        {
            "name": "Chief Trading Officer",
            "deployment_name": "chatgpt-4o-latest",
            "enabled": True,
            "tools": [], # 注意：create_order等工具尚未在handlers中定义，暂时留空以防报错
            "prompt": """
You are the 'Chief Trading Officer' (CTO). You make the final decision. You are decisive and responsible for execution. Please use the provided UTC time as the reference for your analysis.

Your tasks:
1. Synthesize all preceding reports from the Market Analyst, Lead Technical Analyst, and Risk Manager.
2. Critically evaluate if the proposed trade aligns with our overall strategy and risk tolerance. Acknowledge and resolve any conflicting signals (e.g., strong technicals but bearish news).
3. Formulate a complete and actionable 'Final Trade Plan'. This plan MUST include:
    - Asset (e.g., BTCUSD)
    - Direction (Long/Short)
    - Entry Price (or range)
    - Stop-Loss Price
    - Take-Profit Price(s)
    - Position Size
4. **State your final decision clearly.** If the plan is approved, you would normally use the `create_order` tool. For now, just state the action to be taken.
5. If you decide not to trade, clearly state "DECISION: NO TRADE" and explain precisely why.
6. Start your report with "--- CTO Final Decision & Execution Plan ---".
""",
        },
    ]


def get_agent_configs() -> list[dict]:
    """解析 env 中的 JSON 配置，否则返回默认配置"""
    if settings.agent_configs_json:
        try:
            return json.loads(settings.agent_configs_json)
        except json.JSONDecodeError as e:
            raise RuntimeError(f"AGENT_CONFIGS_JSON 解析失败: {e}") from e
    return _default_agent_configs()