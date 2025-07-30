# crypto_news_collector/app/main.py
from contextlib import asynccontextmanager
import os

from fastapi import FastAPI, Query
from sqlalchemy.orm import Session

from app import db
from app.models import NewsEvent

# ---------- FastAPI 生命周期 ---------- #
@asynccontextmanager
async def lifespan(app: FastAPI):
    # 开发环境自动建表
    if os.getenv("ENV", "development") == "development":
        db.Base.metadata.create_all(bind=db.engine)
        print("Startup: Database tables created.")
    yield
    print("Shutdown: Cleaning up resources...")

app = FastAPI(
    title="Crypto News Collector",
    lifespan=lifespan
)

# ---------- 路由 ---------- #
@app.get("/")
def read_root():
    return {"message": "Crypto News Collector is running"}

@app.get("/news-latest")
def news_latest(
    limit: int = Query(100, ge=1, le=500, description="返回条数 1–500"),
    channel: str | None = Query(None, description="仅返回指定来源(频道/群)"),
    keyword: str | None = Query(None, description="消息文本模糊匹配关键字")
):
    """
    获取最新新闻列表，可选按来源或关键字过滤。
    例:
        /news-latest?limit=200
        /news-latest?channel=WatcherGuru
        /news-latest?keyword=bitcoin
        /news-latest?channel=wublockgroup&keyword=trump&limit=50
    """
    session: Session = db.SessionLocal()
    try:
        q = session.query(NewsEvent).order_by(NewsEvent.created_at.desc())

        if channel:
            q = q.filter(NewsEvent.source == channel)

        if keyword:
            like_expr = f"%{keyword}%"
            q = q.filter(NewsEvent.raw_text.ilike(like_expr))

        rows = q.limit(limit).all()

        return [
            {
                "id": r.id,
                "symbol": r.symbol,
                "source": r.source,
                "raw_text": r.raw_text,
                "created_at": r.created_at.isoformat()
            }
            for r in rows
        ]
    finally:
        session.close()

@app.get("/news/{news_id}")
def news_detail(news_id: int):
    """获取单条新闻详情。"""
    session: Session = db.SessionLocal()
    try:
        row = session.get(NewsEvent, news_id)
        if not row:
            return {"message": f"news_id={news_id} not found"}
        return {
            "id": row.id,
            "symbol": row.symbol,
            "source": row.source,
            "raw_text": row.raw_text,
            "created_at": row.created_at.isoformat()
        }
    finally:
        session.close()
