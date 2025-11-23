"""
Data Writer - 单职责：将实时数据写入Parquet冷存储
从MySQL/Redis读取数据，按日期分区写入Parquet文件
减少冗余：只存储回测需要的字段
统一使用UTC时区
"""
import logging
import os
from pathlib import Path
from datetime import datetime, date, timedelta, timezone
from typing import List, Optional, Dict, Any
import pandas as pd
from sqlalchemy.orm import Session
from sqlalchemy import and_

from app.db import SessionLocal
from app.models import MarketData

logger = logging.getLogger(__name__)


class DataWriter:
    """
    数据写入器
    - 从MySQL读取K线数据
    - 按日期分区写入Parquet
    - 减少冗余：只存储回测需要的字段
    """
    
    def __init__(self, base_path: str = "/app/data"):
        """
        初始化数据写入器
        
        Args:
            base_path: 数据存储根路径
        """
        self.base_path = Path(base_path)
        self.candles_path = self.base_path / "candles"
        self.news_path = self.base_path / "news"
        
        # 创建目录
        self.candles_path.mkdir(parents=True, exist_ok=True)
        self.news_path.mkdir(parents=True, exist_ok=True)
        
        logger.info(f"[DataWriter] Initialized with base_path: {base_path}")
    
    def get_writable_date_range(self, symbol: str, timeframe: str) -> tuple[Optional[date], date]:
        """
        获取可写日期范围（增量滚动存储）
        返回: (min_allowed_date, max_allowed_date)
        - 如果目录不存在或没有文件，返回 (None, today)，表示所有日期都可写
        - 否则返回 (latest_date - 1, today)
        
        Args:
            symbol: 交易对
            timeframe: 时间周期
            
        Returns:
            (min_allowed_date, max_allowed_date) 或 (None, today)
        """
        symbol_timeframe_dir = self.candles_path / f"{symbol}_{timeframe}"
        current_date = datetime.now(timezone.utc).date()  # 使用UTC日期
        
        if not symbol_timeframe_dir.exists():
            return (None, current_date)
        
        parquet_files = list(symbol_timeframe_dir.glob("*.parquet"))
        if not parquet_files:
            return (None, current_date)
        
        # 从文件名提取日期
        existing_dates = []
        for file_path in parquet_files:
            try:
                date_str = file_path.stem
                file_date = datetime.strptime(date_str, "%Y-%m-%d").date()
                existing_dates.append(file_date)
            except (ValueError, AttributeError):
                continue
        
        if not existing_dates:
            return (None, current_date)
        
        latest_date = max(existing_dates)
        min_allowed_date = latest_date - timedelta(days=1)
        return (min_allowed_date, current_date)
    
    def _is_date_writable(self, target_date: date, data_dir: Path) -> bool:
        """
        检查目标日期是否允许写入（增量滚动存储）
        只允许覆盖：最新文件日期-1 到 今天
        更早的历史数据保持完整，不允许覆盖
        
        Args:
            target_date: 目标日期
            data_dir: 数据目录（包含 Parquet 文件的目录）
            
        Returns:
            True if writable, False otherwise
        """
        if not data_dir.exists():
            # 目录不存在，允许写入（首次写入）
            return True
        
        # 查找所有已存在的 Parquet 文件
        parquet_files = list(data_dir.glob("*.parquet"))
        if not parquet_files:
            # 没有已存在的文件，允许写入
            return True
        
        # 从文件名提取日期并排序
        existing_dates = []
        for file_path in parquet_files:
            try:
                # 文件名格式：YYYY-MM-DD.parquet
                date_str = file_path.stem
                file_date = datetime.strptime(date_str, "%Y-%m-%d").date()
                existing_dates.append(file_date)
            except (ValueError, AttributeError):
                # 文件名格式不正确，跳过
                continue
        
        if not existing_dates:
            # 没有有效的日期文件，允许写入
            return True
        
        # 找到最新日期
        latest_date = max(existing_dates)
        current_date = datetime.now(timezone.utc).date()  # 使用UTC日期
        
        # 允许写入的日期：最新日期-1 到 今天
        min_allowed_date = latest_date - timedelta(days=1)
        max_allowed_date = current_date
        
        is_writable = min_allowed_date <= target_date <= max_allowed_date
        
        # 不再记录警告日志，因为应该在调用前就过滤掉
        # 这里只作为双重保险，静默返回 False
        return is_writable
    
    def write_candles_for_date(
        self,
        symbol: str,
        timeframe: str,
        target_date: date,
        db: Optional[Session] = None
    ) -> bool:
        """
        将指定日期的K线数据写入Parquet
        
        存储结构：
        - 路径：data/candles/{symbol}_{timeframe}/{YYYY-MM-DD}.parquet
        - 字段：只存储回测需要的字段（OHLCV + 技术指标）
        
        Args:
            symbol: 交易对，如 "BTCUSDT"
            timeframe: 时间周期，如 "1m", "5m"
            target_date: 目标日期
            db: 数据库会话（如果为None则创建新会话）
            
        Returns:
            True if successful, False otherwise
        """
        close_db = False
        if db is None:
            db = SessionLocal()
            close_db = True
        
        try:
            # 计算日期范围（使用UTC时区）
            start_datetime = datetime.combine(target_date, datetime.min.time()).replace(tzinfo=timezone.utc)
            end_datetime = datetime.combine(target_date, datetime.max.time()).replace(tzinfo=timezone.utc)
            
            # 从MySQL查询数据
            records = db.query(MarketData).filter(
                and_(
                    MarketData.symbol == symbol,
                    MarketData.timeframe == timeframe,
                    MarketData.created_at >= start_datetime,
                    MarketData.created_at < end_datetime + pd.Timedelta(days=1)
                )
            ).order_by(MarketData.created_at.asc()).all()
            
            if not records:
                logger.warning(f"[DataWriter] No data found for {symbol} {timeframe} on {target_date}")
                return False
            
            # 转换为DataFrame（只存储回测需要的字段）
            data_list = []
            for record in records:
                # 从created_at提取timestamp（Unix时间戳）
                # 确保created_at是UTC aware（即使数据库存储了时区信息）
                if record.created_at:
                    if record.created_at.tzinfo is None:
                        # 如果没有时区信息，假设是UTC
                        created_at_utc = record.created_at.replace(tzinfo=timezone.utc)
                    elif record.created_at.tzinfo != timezone.utc:
                        # 如果有其他时区，转换为UTC
                        created_at_utc = record.created_at.astimezone(timezone.utc)
                    else:
                        created_at_utc = record.created_at
                    timestamp = created_at_utc.timestamp()
                else:
                    timestamp = 0.0
                
                # 只存储回测需要的字段
                # 注意：MySQL中存储的是latest_price，但我们需要从OHLC数据中提取
                # 由于MySQL中每个timeframe的记录都包含OHLC信息（在intervals_data中），
                # 但实际存储时我们只存储了latest_price，所以需要从Kraken API的原始OHLC数据中获取
                # 这里我们假设从created_at可以推断出K线的时间戳
                
                # 简化：使用latest_price作为close（实际应该从原始OHLC数据获取）
                # 但为了减少冗余，我们只存储技术指标，OHLC需要从原始数据源获取
                # 这里先存储技术指标，OHLC需要从Kraken API的原始数据中获取
                
                row = {
                    "timestamp": timestamp,
                    # 技术指标（回测需要）
                    "ema_9": float(record.ema_9) if record.ema_9 else None,
                    "sma_14": float(record.sma_14) if record.sma_14 else None,
                    "rsi": float(record.rsi) if record.rsi else None,
                    "macd_line": float(record.macd_line) if record.macd_line else None,
                    "macd_signal": float(record.macd_signal) if record.macd_signal else None,
                    "macd_hist": float(record.macd_hist) if record.macd_hist else None,
                    "bollinger_upper": float(record.bollinger_upper) if record.bollinger_upper else None,
                    "bollinger_middle": float(record.bollinger_middle) if record.bollinger_middle else None,
                    "bollinger_lower": float(record.bollinger_lower) if record.bollinger_lower else None,
                    "atr": float(record.atr) if record.atr else None,
                }
                data_list.append(row)
            
            if not data_list:
                logger.warning(f"[DataWriter] No valid data to write for {symbol} {timeframe} on {target_date}")
                return False
            
            # 创建DataFrame
            df = pd.DataFrame(data_list)
            
            # 创建目录
            symbol_timeframe_dir = self.candles_path / f"{symbol}_{timeframe}"
            symbol_timeframe_dir.mkdir(parents=True, exist_ok=True)
            
            # 写入Parquet文件
            file_path = symbol_timeframe_dir / f"{target_date.strftime('%Y-%m-%d')}.parquet"
            
            # 如果文件已存在，读取并合并（去重）
            if file_path.exists():
                try:
                    existing_df = pd.read_parquet(file_path)
                    # 合并并去重（基于timestamp）
                    combined_df = pd.concat([existing_df, df], ignore_index=True)
                    combined_df = combined_df.drop_duplicates(subset=["timestamp"], keep="last")
                    combined_df = combined_df.sort_values("timestamp")
                    df = combined_df
                except Exception as e:
                    # 如果文件损坏或读取失败，记录警告并跳过合并（直接写入新数据）
                    logger.warning(f"[DataWriter] Failed to read existing Parquet file {file_path}: {e}. Writing new data without merge.")
            
            # 写入Parquet（使用压缩）
            df.to_parquet(file_path, compression="snappy", index=False)
            
            logger.info(f"[DataWriter] Wrote {len(df)} records to {file_path}")
            return True
            
        except Exception as e:
            logger.error(f"[DataWriter] Failed to write candles for {symbol} {timeframe} on {target_date}: {e}")
            return False
        finally:
            if close_db:
                db.close()
    
    def write_ohlc_from_kraken(
        self,
        symbol: str,
        timeframe: str,
        target_date: date,
        ohlc_data: List[List[Any]],
        calculate_indicators: bool = True
    ) -> bool:
        """
        从Kraken API的原始OHLC数据写入Parquet（包含技术指标）
        
        这是更准确的方法，因为直接从API获取OHLC数据，不依赖MySQL中的latest_price
        自动过滤未完成的K线，确保只存储已完成的K线数据
        
        Args:
            symbol: 交易对
            timeframe: 时间周期（如 "1m", "5m"）
            target_date: 目标日期
            ohlc_data: Kraken API返回的OHLC数据列表
                     格式: [[timestamp, open, high, low, close, vwap, volume, count], ...]
            calculate_indicators: 是否计算技术指标
            
        Returns:
            True if successful, False otherwise
        """
        try:
            # 计算当前时间（用于过滤未完成的K线，使用UTC）
            current_time = datetime.now(timezone.utc).timestamp()
            
            # 解析timeframe获取interval秒数（"1m" -> 60, "5m" -> 300）
            try:
                interval_minutes = int(timeframe.rstrip('m'))
                interval_seconds = interval_minutes * 60
            except (ValueError, AttributeError):
                # 如果timeframe格式不正确，默认使用60秒（1分钟）
                logger.warning(f"[DataWriter] Invalid timeframe format: {timeframe}, using 60 seconds")
                interval_seconds = 60
            
            # 转换为DataFrame
            data_list = []
            # 计算目标日期的UTC时间戳范围
            target_timestamp_start = datetime.combine(target_date, datetime.min.time()).replace(tzinfo=timezone.utc).timestamp()
            target_timestamp_end = datetime.combine(target_date, datetime.max.time()).replace(tzinfo=timezone.utc).timestamp()
            
            filtered_count = 0
            for item in ohlc_data:
                # Kraken OHLC格式: [time, open, high, low, close, vwap, volume, count]
                if len(item) < 6:
                    continue
                
                timestamp = float(item[0])  # Unix时间戳
                
                # 只处理目标日期的数据
                if timestamp < target_timestamp_start or timestamp >= target_timestamp_end + 86400:
                    continue
                
                # ====== 关键：过滤未完成的K线 ======
                # 只保留至少一个K线周期前的数据（确保K线已完成）
                time_diff = current_time - timestamp
                if time_diff < interval_seconds:
                    # 这条K线可能还未完成，跳过
                    filtered_count += 1
                    logger.debug(
                        f"[DataWriter] Skipping possibly ongoing candle: "
                        f"timestamp={timestamp}, time_diff={time_diff:.1f}s < {interval_seconds}s"
                    )
                    continue
                
                row = {
                    "timestamp": timestamp,
                    "open": float(item[1]),
                    "high": float(item[2]),
                    "low": float(item[3]),
                    "close": float(item[4]),
                    "volume": float(item[6]) if len(item) > 6 else 0.0,
                }
                data_list.append(row)
            
            if filtered_count > 0:
                logger.info(f"[DataWriter] Filtered out {filtered_count} possibly ongoing candles for {symbol} {timeframe}")
            
            if not data_list:
                logger.warning(f"[DataWriter] No OHLC data for {symbol} {timeframe} on {target_date}")
                return False
            
            # 创建DataFrame
            df = pd.DataFrame(data_list)
            df = df.sort_values("timestamp")
            
            # 创建目录
            symbol_timeframe_dir = self.candles_path / f"{symbol}_{timeframe}"
            symbol_timeframe_dir.mkdir(parents=True, exist_ok=True)
            
            # ====== 增量滚动存储：只允许覆盖最新日期-1到今天 ======
            # 双重保险：如果日期不可写，静默跳过（应该在调用前就过滤掉）
            if not self._is_date_writable(target_date, symbol_timeframe_dir):
                return False
            
            # 写入Parquet文件
            file_path = symbol_timeframe_dir / f"{target_date.strftime('%Y-%m-%d')}.parquet"
            
            # 如果文件已存在，读取并合并（去重）
            if file_path.exists():
                try:
                    existing_df = pd.read_parquet(file_path)
                    # 合并并去重（基于timestamp）
                    combined_df = pd.concat([existing_df, df], ignore_index=True)
                    combined_df = combined_df.drop_duplicates(subset=["timestamp"], keep="last")
                    combined_df = combined_df.sort_values("timestamp")
                    df = combined_df
                except Exception as e:
                    # 如果文件损坏或读取失败，记录警告并跳过合并（直接写入新数据）
                    logger.warning(f"[DataWriter] Failed to read existing Parquet file {file_path}: {e}. Writing new data without merge.")
            
            # 计算技术指标（如果需要）
            if calculate_indicators and len(df) > 0:
                df = self._calculate_indicators(df)
            
            # 写入Parquet（使用压缩）
            df.to_parquet(file_path, compression="snappy", index=False)
            
            logger.info(f"[DataWriter] Wrote {len(df)} OHLC records (with indicators) to {file_path}")
            return True
            
        except Exception as e:
            logger.error(f"[DataWriter] Failed to write OHLC for {symbol} {timeframe} on {target_date}: {e}")
            return False
    
    def _calculate_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        计算技术指标并添加到DataFrame
        
        Args:
            df: 包含OHLC数据的DataFrame
            
        Returns:
            添加了技术指标的DataFrame
        """
        if "close" not in df.columns or len(df) == 0:
            return df
        
        closes = df["close"].values
        highs = df["high"].values
        lows = df["low"].values
        
        # 计算EMA
        df["ema_9"] = df["close"].ewm(span=9, adjust=False).mean()
        
        # 计算SMA
        df["sma_14"] = df["close"].rolling(window=14).mean()
        
        # 计算RSI
        delta = df["close"].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        df["rsi"] = 100 - (100 / (1 + rs))
        
        # 计算MACD
        ema_12 = df["close"].ewm(span=12, adjust=False).mean()
        ema_26 = df["close"].ewm(span=26, adjust=False).mean()
        df["macd_line"] = ema_12 - ema_26
        df["macd_signal"] = df["macd_line"].ewm(span=9, adjust=False).mean()
        df["macd_hist"] = df["macd_line"] - df["macd_signal"]
        
        # 计算布林带
        sma_20 = df["close"].rolling(window=20).mean()
        std_20 = df["close"].rolling(window=20).std()
        df["bollinger_upper"] = sma_20 + (std_20 * 2)
        df["bollinger_middle"] = sma_20
        df["bollinger_lower"] = sma_20 - (std_20 * 2)
        
        # 计算ATR
        high_low = df["high"] - df["low"]
        high_close = (df["high"] - df["close"].shift(1)).abs()
        low_close = (df["low"] - df["close"].shift(1)).abs()
        tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
        df["atr"] = tr.rolling(window=14).mean()
        
        return df
    
    def write_news_for_date(
        self,
        target_date: date,
        news_items: List[Dict[str, Any]]
    ) -> bool:
        """
        将指定日期的新闻数据写入Parquet
        
        存储结构：
        - 路径：data/news/{YYYY-MM-DD}.parquet
        - 统一使用timestamp字段（Unix时间戳，float）
        
        Args:
            target_date: 目标日期
            news_items: 新闻项列表（包含原始新闻和标注信息）
            
        Returns:
            True if successful, False otherwise
        """
        try:
            if not news_items:
                logger.warning(f"[DataWriter] No news items for {target_date}")
                return False
            
            # 统一时间戳格式：确保timestamp字段存在（Unix时间戳）
            for item in news_items:
                if "timestamp" not in item:
                    # 从ts字段转换（可能是ISO字符串或Unix时间戳字符串）
                    ts = item.get("ts", "")
                    if ts:
                        try:
                            # 尝试解析为Unix时间戳
                            item["timestamp"] = float(ts)
                        except (ValueError, TypeError):
                            # 解析ISO8601字符串
                            try:
                                dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                                item["timestamp"] = dt.timestamp()
                            except Exception:
                                logger.warning(f"[DataWriter] Failed to parse ts: {ts}")
                                item["timestamp"] = 0.0
                    else:
                        item["timestamp"] = 0.0
            
            # 转换为DataFrame
            df = pd.DataFrame(news_items)
            
            # 写入Parquet文件
            file_path = self.news_path / f"{target_date.strftime('%Y-%m-%d')}.parquet"
            
            # 如果文件已存在，读取并合并（去重）
            if file_path.exists():
                existing_df = pd.read_parquet(file_path)
                # 合并并去重（基于key或message_id）
                key_col = "key" if "key" in df.columns else "message_id"
                if key_col in df.columns and key_col in existing_df.columns:
                    combined_df = pd.concat([existing_df, df], ignore_index=True)
                    combined_df = combined_df.drop_duplicates(subset=[key_col], keep="last")
                    df = combined_df
                else:
                    df = pd.concat([existing_df, df], ignore_index=True)
            
            # 写入Parquet（使用压缩）
            df.to_parquet(file_path, compression="snappy", index=False)
            
            logger.info(f"[DataWriter] Wrote {len(df)} news items to {file_path}")
            return True
            
        except Exception as e:
            logger.error(f"[DataWriter] Failed to write news for {target_date}: {e}")
            return False


# Singleton
data_writer = DataWriter()

