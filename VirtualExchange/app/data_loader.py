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
        start_time: datetime,
        end_time: datetime,
        timeframe: str = "1m"
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
        
        # 检测数据缺失（warn策略）
        if candles:
            self._detect_missing_candles(candles, timeframe, start_time, end_time)
        
        logger.info(f"[DataLoader] Total loaded: {len(candles)} candles for {symbol} {timeframe}")
        
        return candles
    
    def _parse_timeframe_seconds(self, timeframe: str) -> int:
        """解析timeframe为秒数"""
        try:
            if timeframe.endswith('m'):
                return int(timeframe[:-1]) * 60
            elif timeframe.endswith('h'):
                return int(timeframe[:-1]) * 3600
            elif timeframe.endswith('d'):
                return int(timeframe[:-1]) * 86400
            else:
                return 60  # 默认1分钟
        except (ValueError, AttributeError):
            return 60
    
    def _detect_missing_candles(self, candles: List[OHLC], timeframe: str, start_time: datetime, end_time: datetime) -> None:
        """
        检测缺失的K线数据（warn策略：记录警告但继续）
        
        Args:
            candles: 已加载的K线列表（已排序）
            timeframe: 时间周期
            start_time: 开始时间
            end_time: 结束时间
        """
        if not candles:
            return
        
        interval_seconds = self._parse_timeframe_seconds(timeframe)
        start_ts = start_time.timestamp()
        end_ts = end_time.timestamp()
        
        missing_gaps = []
        prev_ts = None
        
        for candle in candles:
            current_ts = candle.timestamp
            
            # 跳过范围外的数据
            if current_ts < start_ts or current_ts > end_ts:
                continue
            
            if prev_ts is not None:
                gap = current_ts - prev_ts
                # 如果gap超过1.5倍间隔，认为有缺失（允许0.5倍容差）
                if gap > interval_seconds * 1.5:
                    # 缺失数量 = gap内的K线数 - 1（减去当前这根）
                    missing_count = max(0, int(gap / interval_seconds) - 1)
                    if missing_count > 0:
                        gap_start = datetime.fromtimestamp(prev_ts + interval_seconds, tz=timezone.utc)
                        gap_end = datetime.fromtimestamp(current_ts - interval_seconds, tz=timezone.utc)
                        missing_gaps.append({
                            "start": gap_start,
                            "end": gap_end,
                            "missing_count": missing_count,
                            "gap_seconds": gap
                        })
            
            prev_ts = current_ts
        
        # 检查开头和结尾的缺失
        first_ts = candles[0].timestamp
        if first_ts > start_ts + interval_seconds * 1.5:
            missing_count = max(0, int((first_ts - start_ts) / interval_seconds) - 1)
            if missing_count > 0:
                gap_start = datetime.fromtimestamp(start_ts, tz=timezone.utc)
                gap_end = datetime.fromtimestamp(first_ts - interval_seconds, tz=timezone.utc)
                missing_gaps.insert(0, {
                    "start": gap_start,
                    "end": gap_end,
                    "missing_count": missing_count,
                    "gap_seconds": first_ts - start_ts
                })
        
        last_ts = candles[-1].timestamp
        if last_ts < end_ts - interval_seconds * 1.5:
            missing_count = max(0, int((end_ts - last_ts) / interval_seconds) - 1)
            if missing_count > 0:
                gap_start = datetime.fromtimestamp(last_ts + interval_seconds, tz=timezone.utc)
                gap_end = datetime.fromtimestamp(end_ts, tz=timezone.utc)
                missing_gaps.append({
                    "start": gap_start,
                    "end": gap_end,
                    "missing_count": missing_count,
                    "gap_seconds": end_ts - last_ts
                })
        
        # 记录警告
        if missing_gaps:
            total_missing = sum(g["missing_count"] for g in missing_gaps)
            logger.warning(
                f"[DataLoader] Detected {len(missing_gaps)} missing candle gaps "
                f"(total {total_missing} missing candles):"
            )
            for gap in missing_gaps:
                logger.warning(
                    f"  Missing {gap['missing_count']} candles from {gap['start']} to {gap['end']} "
                    f"(gap: {gap['gap_seconds']:.0f}s)"
                )
    
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

