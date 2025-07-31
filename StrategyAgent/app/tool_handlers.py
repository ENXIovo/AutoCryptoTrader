from .tool_router import ToolRouter
from .config import settings

# 实例化路由器
news_router = ToolRouter(base_url=settings.news_service_url)

# 将工具名映射到具体执行函数
TOOL_HANDLERS = {
    "latest_news": news_router.latest_news,
    # 以后可继续添加其他工具
}
