"""
Data Loader - 单职责：从M2 DataStore加载历史K线数据
支持Parquet/CSV格式，按日期分区
统一使用UTC时区
"""
import logging
import os
from typing import List, Optional
from datetime import datetime, timedelta, timezone
from pathlib import Path
import pandas as pd
from app.models import OHLC
from app.utils.time_utils import ensure_utc

logger = logging.getLogger(__name__)


class DataLoader:
    """
    历史K线数据加载器
    - 从M2 DataStore加载Parquet/CSV文件
    - 支持按日期分区
    - 返回标准化的OHLC数据
    """
    
    def __init__(self, data_store_path: str = "/app/data"):
        """
        初始化数据加载器
        
        Args:
            data_store_path: M2 DataStore根路径（包含candles和news目录）
        """
        self.base_path = Path(data_store_path)
        self.candles_path = self.base_path / "candles"
        logger.info(f"[DataLoader] Initialized with path: {data_store_path}")
    
    def load_candles(
        self,
        symbol: str,
        timeframe: str = "1m",
        start_time: datetime,
        end_time: datetime
    ) -> List[OHLC]:
        """
        加载历史K线数据
        
        文件路径格式：data/candles/{SYMBOL}_{TIMEFRAME}/{YYYY-MM-DD}.parquet
        
        Args:
            symbol: 交易对，如 "BTCUSDT"
            timeframe: 时间周期，如 "1m", "5m", "1h"
            start_time: 开始时间（自动转换为UTC）
            end_time: 结束时间（自动转换为UTC）
            
        Returns:
            OHLC列表
        """
        # 确保时区为UTC
        start_time = ensure_utc(start_time)
        end_time = ensure_utc(end_time)
        
        candles = []
        current_date = start_time.date()
        end_date = end_time.date()
        
        while current_date <= end_date:
            # 构建文件路径（新格式：data/candles/{SYMBOL}_{TIMEFRAME}/{YYYY-MM-DD}.parquet）
            file_path = self.candles_path / f"{symbol}_{timeframe}" / f"{current_date.strftime('%Y-%m-%d')}.parquet"
            
            if file_path.exists():
                try:
                    # 读取Parquet文件
                    df = pd.read_parquet(file_path)
                    
                    # 标准化列名（支持多种格式）
                    # 确保所有时间戳都使用UTC时区
                    if "timestamp" not in df.columns and "time" in df.columns:
                        # 如果time列是字符串/日期格式，转换为UTC aware datetime再转时间戳
                        df["timestamp"] = pd.to_datetime(df["time"], utc=True).astype(int) / 1000
                    elif "timestamp" not in df.columns and "ts" in df.columns:
                        # 如果ts列是字符串/日期格式，转换为UTC aware datetime再转时间戳
                        df["timestamp"] = pd.to_datetime(df["ts"], utc=True).astype(int) / 1000
                    
                    # 过滤时间范围
                    if "timestamp" in df.columns:
                        df = df[
                            (df["timestamp"] >= start_time.timestamp()) &
                            (df["timestamp"] <= end_time.timestamp())
                        ]
                    
                    # 转换为OHLC对象
                    for _, row in df.iterrows():
                        candle = OHLC(
                            timestamp=float(row.get("timestamp", 0)),
                            open=float(row.get("open", row.get("o", 0))),
                            high=float(row.get("high", row.get("h", 0))),
                            low=float(row.get("low", row.get("l", 0))),
                            close=float(row.get("close", row.get("c", 0))),
                            volume=float(row.get("volume", row.get("v", 0)))
                        )
                        candles.append(candle)
                    
                    logger.info(f"[DataLoader] Loaded {len(candles)} candles from {file_path}")
                except Exception as e:
                    logger.warning(f"[DataLoader] Failed to load {file_path}: {e}")
            else:
                logger.warning(f"[DataLoader] File not found: {file_path}")
            
            current_date += timedelta(days=1)
        
        # 按时间排序
        candles.sort(key=lambda x: x.timestamp)
        logger.info(f"[DataLoader] Total loaded: {len(candles)} candles for {symbol} {timeframe}")
        
        return candles
    
    def get_latest_price(self, symbol: str, timestamp: float) -> Optional[float]:
        """
        获取指定时间点的最新价格（用于Mock DataCollector）
        
        Args:
            symbol: 交易对
            timestamp: 时间戳
            
        Returns:
            最新价格，如果找不到则返回None
        """
        # 简化实现：从最近的K线数据中获取
        # 实际应该从已加载的数据中查找
        # 这里先返回None，由backtest_runner维护价格缓存
        return None

