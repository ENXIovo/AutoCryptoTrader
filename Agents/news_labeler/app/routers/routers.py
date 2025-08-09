from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Query

from ..models import NewsItem
from ..services.topnews_service import get_top_news

router = APIRouter()


@router.get("/top-news", response_model=List[NewsItem])
def top_news(
    limit: int = Query(20, ge=1, le=200),
    period: Optional[str] = Query(None, description="day|week|month"),
    refresh: bool = Query(True, description="recompute before returning"),
):
    return get_top_news(limit=limit, period=period, refresh=refresh)


@router.get("/health")
def health():
    return {"ok": True}
