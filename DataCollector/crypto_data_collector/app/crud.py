# app/crud.py

from sqlalchemy.orm import Session
from app.models import MarketData

def save_market_data(db: Session, data: dict) -> MarketData:
    """
    将多种API获取的数据存储到同一行/同一表中。
    data示例:
    {
       "symbol": "BTCUSDT",
       "latest_price": 20835.12,
       "bid_price": 20835.10,
       "ask_price": 20835.20,
       "price_change": -94.99,
       "volume_24h": 431.0
    }
    """
    market_data = MarketData(**data)
    db.add(market_data)
    db.commit()
    db.refresh(market_data)
    return market_data
