from .tool_router import ToolRouter
from .config import settings

"""
此模块将工具名称映射到可以执行的具体函数。为了保持职责分离，
StrategyAgent 本身不会直接处理其他服务的逻辑，而是通过调用
外部 HTTP API 来获得数据。新增的 ``kraken_filter`` 和 ``gpt_latest``
工具分别调用 KrakenService 的 ``/kraken-filter`` 端点和
DataCollector 的 ``/gpt-latest/{symbol}`` 端点。
"""

# 实例化路由器
news_router = ToolRouter(base_url=settings.news_service_url)

# 将工具名映射到具体执行函数
TOOL_HANDLERS = {
    "latest_news": news_router.latest_news,
    "kraken_filter": news_router.kraken_filter,
    "gpt_latest": news_router.gpt_latest,
    # 以后可继续添加其他工具
}
