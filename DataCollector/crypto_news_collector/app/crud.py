# app/crud.py

from sqlalchemy.orm import Session
from app.models import NewsEvent

def save_news_event(db: Session, data: dict) -> NewsEvent:
   obj = NewsEvent(**data)
   db.add(obj)
   db.commit()
   db.refresh(obj)
   return obj
