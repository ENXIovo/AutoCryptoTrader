"""
Data Loader - 单职责：从Parquet冷存储加载数据
提供统一的访问API：load_candles, load_news
"""
import logging
from pathlib import Path
from typing import List, Optional
from datetime import datetime, date, timedelta, timezone
import pandas as pd

logger = logging.getLogger(__name__)


def load_candles(
    symbol: str,
    timeframe: str,
    start: datetime,
    end: datetime,
    base_path: str = "/app/data"
) -> pd.DataFrame:
    """
    从Parquet冷存储加载K线数据
    
    Args:
        symbol: 交易对，如 "BTCUSDT"
        timeframe: 时间周期，如 "1m", "5m"
        start: 开始时间
        end: 结束时间
        base_path: 数据存储根路径
        
    Returns:
        DataFrame with columns: timestamp, open, high, low, close, volume, [indicators...]
    """
    base = Path(base_path)
    candles_path = base / "candles" / f"{symbol}_{timeframe}"
    
    if not candles_path.exists():
        logger.warning(f"[DataLoader] Path not found: {candles_path}")
        return pd.DataFrame()
    
    # 收集所有需要读取的文件
    files_to_read = []
    current_date = start.date()
    end_date = end.date()
    
    while current_date <= end_date:
        file_path = candles_path / f"{current_date.strftime('%Y-%m-%d')}.parquet"
        if file_path.exists():
            files_to_read.append(file_path)
        current_date += timedelta(days=1)
    
    if not files_to_read:
        logger.warning(f"[DataLoader] No data files found for {symbol} {timeframe} between {start} and {end}")
        return pd.DataFrame()
    
    # 读取并合并所有文件
    dfs = []
    for file_path in files_to_read:
        try:
            df = pd.read_parquet(file_path)
            dfs.append(df)
        except Exception as e:
            logger.error(f"[DataLoader] Failed to read {file_path}: {e}")
            continue
    
    if not dfs:
        return pd.DataFrame()
    
    # 合并所有DataFrame
    combined_df = pd.concat(dfs, ignore_index=True)
    
    # 过滤时间范围（确保使用UTC时间戳）
    if "timestamp" in combined_df.columns:
        # 确保 start 和 end 是 UTC aware
        if start.tzinfo is None:
            start = start.replace(tzinfo=timezone.utc)
        if end.tzinfo is None:
            end = end.replace(tzinfo=timezone.utc)
        start_ts = start.timestamp()
        end_ts = end.timestamp()
        combined_df = combined_df[
            (combined_df["timestamp"] >= start_ts) &
            (combined_df["timestamp"] <= end_ts)
        ]
        combined_df = combined_df.sort_values("timestamp")
    
    logger.info(f"[DataLoader] Loaded {len(combined_df)} candles for {symbol} {timeframe}")
    return combined_df


def load_news(
    start: datetime,
    end: datetime,
    base_path: str = "/app/data",
    filters: Optional[dict] = None
) -> pd.DataFrame:
    """
    从Parquet冷存储加载新闻数据
    
    Args:
        start: 开始时间
        end: 结束时间
        base_path: 数据存储根路径
        filters: 可选的过滤条件，如 {"category": "regulation", "importance": ">0.7"}
        
    Returns:
        DataFrame with news items
    """
    base = Path(base_path)
    news_path = base / "news"
    
    if not news_path.exists():
        logger.warning(f"[DataLoader] Path not found: {news_path}")
        return pd.DataFrame()
    
    # 收集所有需要读取的文件
    files_to_read = []
    current_date = start.date()
    end_date = end.date()
    
    while current_date <= end_date:
        file_path = news_path / f"{current_date.strftime('%Y-%m-%d')}.parquet"
        if file_path.exists():
            files_to_read.append(file_path)
        current_date += timedelta(days=1)
    
    if not files_to_read:
        logger.warning(f"[DataLoader] No news files found between {start} and {end}")
        return pd.DataFrame()
    
    # 读取并合并所有文件
    dfs = []
    for file_path in files_to_read:
        try:
            df = pd.read_parquet(file_path)
            dfs.append(df)
        except Exception as e:
            logger.error(f"[DataLoader] Failed to read {file_path}: {e}")
            continue
    
    if not dfs:
        return pd.DataFrame()
    
    # 合并所有DataFrame
    combined_df = pd.concat(dfs, ignore_index=True)
    
    # 过滤时间范围：统一使用timestamp字段（Unix时间戳，UTC）
    # 确保 start 和 end 是 UTC aware
    if start.tzinfo is None:
        start = start.replace(tzinfo=timezone.utc)
    if end.tzinfo is None:
        end = end.replace(tzinfo=timezone.utc)
    start_ts = start.timestamp()
    end_ts = end.timestamp()
    
    if "timestamp" in combined_df.columns:
        combined_df = combined_df[
            (combined_df["timestamp"] >= start_ts) &
            (combined_df["timestamp"] <= end_ts)
        ]
    elif "ts" in combined_df.columns:
        # 向后兼容：从ts字段转换为timestamp
        try:
            # 尝试解析为Unix时间戳（字符串）
            combined_df["timestamp"] = pd.to_numeric(combined_df["ts"], errors="coerce")
            # 如果转换失败，尝试解析ISO字符串
            mask = combined_df["timestamp"].isna()
            if mask.any():
                combined_df.loc[mask, "timestamp"] = pd.to_datetime(
                    combined_df.loc[mask, "ts"]
                ).apply(lambda x: x.timestamp() if pd.notna(x) else None)
            # 过滤时间范围
            combined_df = combined_df[
                (combined_df["timestamp"] >= start_ts) &
                (combined_df["timestamp"] <= end_ts)
            ]
        except Exception:
            logger.warning("[DataLoader] Failed to parse ts field, skipping time filter")
    
    # 应用过滤条件
    if filters:
        for key, value in filters.items():
            if key in combined_df.columns:
                if isinstance(value, str) and value.startswith(">"):
                    threshold = float(value[1:])
                    combined_df = combined_df[combined_df[key].astype(float) > threshold]
                elif isinstance(value, str) and value.startswith("<"):
                    threshold = float(value[1:])
                    combined_df = combined_df[combined_df[key].astype(float) < threshold]
                else:
                    combined_df = combined_df[combined_df[key] == value]
    
    logger.info(f"[DataLoader] Loaded {len(combined_df)} news items")
    return combined_df

