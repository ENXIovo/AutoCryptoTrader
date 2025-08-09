from __future__ import annotations

import logging

from fastapi import FastAPI

from .routers.routers import router as topnews_router

logger = logging.getLogger(__name__)

app = FastAPI(title="News Labeler API")

# 只做装配，不放业务/模型/工具函数
app.include_router(topnews_router)
