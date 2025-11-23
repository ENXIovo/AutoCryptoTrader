"""
News Data Writer - 单职责：将已标注的News数据写入Parquet冷存储
从Redis读取已标注的新闻，按日期分区写入Parquet文件
统一使用UTC时区
"""
import logging
from pathlib import Path
from datetime import datetime, date, timedelta, timezone
from typing import List, Dict, Any, Optional
import pandas as pd

logger = logging.getLogger(__name__)


class NewsDataWriter:
    """
    News数据写入器
    - 从Redis读取已标注的新闻数据
    - 按日期分区写入Parquet
    """
    
    def __init__(self, base_path: str = "/app/data"):
        """
        初始化数据写入器
        
        Args:
            base_path: 数据存储根路径
        """
        self.base_path = Path(base_path)
        self.news_path = self.base_path / "news"
        
        # 创建目录
        self.news_path.mkdir(parents=True, exist_ok=True)
        
        logger.info(f"[NewsDataWriter] Initialized with base_path: {base_path}")
    
    def get_writable_date_range(self) -> tuple[Optional[date], date]:
        """
        获取可写日期范围（增量滚动存储）
        返回: (min_allowed_date, max_allowed_date)
        - 如果目录不存在或没有文件，返回 (None, today)，表示所有日期都可写
        - 否则返回 (latest_date - 1, today)
        
        Returns:
            (min_allowed_date, max_allowed_date) 或 (None, today)
        """
        current_date = datetime.now(timezone.utc).date()  # 使用UTC日期
        
        if not self.news_path.exists():
            return (None, current_date)
        
        parquet_files = list(self.news_path.glob("*.parquet"))
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
    
    def _is_date_writable(self, target_date: date) -> bool:
        """
        检查目标日期是否允许写入（增量滚动存储）
        只允许覆盖：最新文件日期-1 到 今天
        更早的历史数据保持完整，不允许覆盖
        
        Args:
            target_date: 目标日期
            
        Returns:
            True if writable, False otherwise
        """
        if not self.news_path.exists():
            # 目录不存在，允许写入（首次写入）
            return True
        
        # 查找所有已存在的 Parquet 文件
        parquet_files = list(self.news_path.glob("*.parquet"))
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
                logger.warning(f"[NewsDataWriter] No news items for {target_date}")
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
                                logger.warning(f"[NewsDataWriter] Failed to parse ts: {ts}")
                                item["timestamp"] = 0.0
                    else:
                        item["timestamp"] = 0.0
            
            # 转换为DataFrame
            df = pd.DataFrame(news_items)
            
            # ====== 增量滚动存储：只允许覆盖最新日期-1到今天 ======
            # 双重保险：如果日期不可写，静默跳过（应该在调用前就过滤掉）
            if not self._is_date_writable(target_date):
                return False
            
            # 写入Parquet文件
            file_path = self.news_path / f"{target_date.strftime('%Y-%m-%d')}.parquet"
            
            # 如果文件已存在，读取并合并（去重）
            if file_path.exists():
                try:
                    existing_df = pd.read_parquet(file_path)
                    # 合并并去重（基于key或message_id）
                    key_col = "key" if "key" in df.columns else "message_id"
                    if key_col in df.columns and key_col in existing_df.columns:
                        combined_df = pd.concat([existing_df, df], ignore_index=True)
                        combined_df = combined_df.drop_duplicates(subset=[key_col], keep="last")
                        df = combined_df
                    else:
                        df = pd.concat([existing_df, df], ignore_index=True)
                except Exception as e:
                    # 如果文件损坏或读取失败，记录警告并跳过合并（直接写入新数据）
                    logger.warning(f"[NewsDataWriter] Failed to read existing Parquet file {file_path}: {e}. Writing new data without merge.")
            
            # 写入Parquet（使用压缩）
            df.to_parquet(file_path, compression="snappy", index=False)
            
            logger.info(f"[NewsDataWriter] Wrote {len(df)} news items to {file_path}")
            return True
            
        except Exception as e:
            logger.error(f"[NewsDataWriter] Failed to write news for {target_date}: {e}")
            return False


# Singleton
news_data_writer = NewsDataWriter()

