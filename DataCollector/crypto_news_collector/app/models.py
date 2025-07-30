# app/models.py

from sqlalchemy import Column, String, Integer, DateTime
from sqlalchemy.sql import func
from app.db import Base

class NewsEvent(Base):
    __tablename__ = "news_event"

    id = Column(Integer, primary_key=True, index=True)
    symbol = Column(String(20), index=True, nullable=True)
    source = Column(String(100))
    raw_text = Column(String(2000))
    created_at = Column(DateTime(timezone=True), server_default=func.now())