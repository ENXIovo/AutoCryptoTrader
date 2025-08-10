from .tool_router import NewsClient, KrakenClient, DataClient
from .config import settings
from .rrr import calc_rrr_batch

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

def _getTopNews_fixed(**_ignored) -> list[dict]:
    return news_client.getTopNews(limit=settings.news_top_limit, period=None)

def calcRRR(**kwargs) -> dict:
    """
    纯数学 RRR 批量计算器。
    期望参数: { "cases": [ { "entry":..., "stop":..., "tp1":..., "tp2":... }, ... ] }
    """
    cases = kwargs.get("cases") or []
    if not isinstance(cases, list):
        raise ValueError("calcRRR expects 'cases' as a list")
    return calc_rrr_batch(cases)

TOOL_HANDLERS = {
    "getTopNews": _getTopNews_fixed,
    "getAccountInfo": kraken_client.getAccountInfo,
    "getKlineIndicators": data_client.getKlineIndicators,
    "calcRRR": calcRRR,
}
