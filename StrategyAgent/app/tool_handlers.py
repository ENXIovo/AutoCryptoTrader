from .tool_router import NewsClient, KrakenClient, DataClient
from .config import settings

"""
此模块将工具名称映射到可以执行的具体函数。为了保持职责分离，
StrategyAgent 本身不会直接处理其他服务的逻辑，而是通过调用
外部 HTTP API 来获得数据。新增的 ``kraken_filter`` 和 ``gpt_latest``
工具分别调用 KrakenService 的 ``/kraken-filter`` 端点和
DataCollector 的 ``/gpt-latest/{symbol}`` 端点。
"""

# 实例化路由器
news_client = NewsClient(settings.news_service_url)
kraken_client = KrakenClient(settings.kraken_service_url)
data_client = DataClient(settings.data_service_url)

TOOL_HANDLERS = {
    "getCryptoNews": news_client.getCryptoNews,
    "getAccountInfo": kraken_client.getAccountInfo,
    "getKlineIndicators": data_client.getKlineIndicators,
    # 以后再新增其它工具，只需在这里扩展映射
    # 以后可继续添加其他工具
}
