# app/models.py

from sqlalchemy import Column, Float, String, Integer, DateTime, DECIMAL
from sqlalchemy.sql import func
from app.db import Base

class MarketData(Base):
    __tablename__ = "market_data"

    id = Column(Integer, primary_key=True, index=True)
    symbol = Column(String(20), index=True)
    timeframe = Column(String(10), index=True)

    # 基础行情数据 (Ticker)
    latest_price = Column(DECIMAL(20, 12))      
    bid_price = Column(DECIMAL(20, 12))        
    ask_price = Column(DECIMAL(20, 12))        
    volume_24h = Column(DECIMAL(30, 18))       
    high_24h = Column(DECIMAL(20, 12))         
    low_24h = Column(DECIMAL(20, 12))          

    # 订单簿信息 (前 depth 档)
    top_ask_price = Column(DECIMAL(30, 18))
    top_ask_volume = Column(DECIMAL(30, 18))
    top_bid_price = Column(DECIMAL(30, 18))
    top_bid_volume = Column(DECIMAL(30, 18))
    total_bid_volume = Column(DECIMAL(30, 18))       # 新增: 前 depth 档总买量
    total_ask_volume = Column(DECIMAL(30, 18))       # 新增: 前 depth 档总卖量
    bid_ask_volume_ratio = Column(DECIMAL(20, 8))    # 新增: 买卖挂单量比
    spread = Column(DECIMAL(20, 12))                 # 新增: (top_ask_price - top_bid_price)

    # 技术指标 (基于 OHLC)
    ema_9 = Column(DECIMAL(20, 12))
    sma_14 = Column(DECIMAL(20, 12))
    rsi = Column(DECIMAL(5, 2))
    macd_line = Column(DECIMAL(20, 12))              # 新增 MACD
    macd_signal = Column(DECIMAL(20, 12))            
    macd_hist = Column(DECIMAL(20, 12))
    bollinger_upper = Column(DECIMAL(20, 12))        # 新增 布林带
    bollinger_middle = Column(DECIMAL(20, 12))
    bollinger_lower = Column(DECIMAL(20, 12))
    atr = Column(DECIMAL(20, 12))                    # 新增 ATR (14周期)

    # 最近成交信息
    recent_buy_count = Column(Integer)
    recent_sell_count = Column(Integer)
    total_buy_volume = Column(DECIMAL(30, 18))       # 新增: 最近成交总买量
    total_sell_volume = Column(DECIMAL(30, 18))      # 新增: 最近成交总卖量
    buy_sell_volume_ratio = Column(DECIMAL(20, 8))   # 新增: 买卖总量比

    # 创建时间
    created_at = Column(DateTime(timezone=True), server_default=func.now())
