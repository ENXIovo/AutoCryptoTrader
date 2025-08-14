# app/ledger.py
import redis
from typing import Dict, Optional, List

from app.config import settings
from app.models import TradeLedgerEntry, TradeStatus

class TradeLedger:
    """
    一个用于管理Redis中交易台账的封装类。
    它处理所有与交易状态持久化相关的底层操作。
    """
    def __init__(self, redis_url: str):
        """
        初始化Ledger，连接到指定的Redis数据库。
        """
        # 单条交易按 trade_id 存储
        self.trade_hash_key = "trades"
        # 索引：按标准化交易对（altname）映射到 trade_id 集合
        self.symbol_index_prefix = "index:symbol:"
        try:
            self.client = redis.Redis.from_url(redis_url, decode_responses=True)
            self.client.ping()
            import logging as _logging
            _logging.getLogger(__name__).info("Successfully connected to Ledger Redis.")
        except redis.exceptions.ConnectionError as e:
            import logging as _logging
            _logging.getLogger(__name__).info(f"FATAL: Could not connect to Ledger Redis at {redis_url}. Error: {e}")
            # 这里的raise会让应用在无法连接到Redis时启动失败，这通常是期望的行为
            raise

    def write_trade(self, trade: TradeLedgerEntry) -> None:
        """写入/更新单笔交易，并维护 symbol 索引。"""
        try:
            self.client.hset(self.trade_hash_key, trade.trade_id, trade.model_dump_json())
            self.client.sadd(self._symbol_index_key(trade.symbol), trade.trade_id)
            import logging as _logging
            _logging.getLogger(__name__).info(f"Ledger: Wrote/Updated trade {trade.trade_id} for {trade.symbol}")
        except redis.exceptions.RedisError as e:
            import logging as _logging
            _logging.getLogger(__name__).info(f"Error writing to Redis ledger for {trade.symbol}: {e}")
            raise

    def get_trade(self, symbol: str) -> Optional[TradeLedgerEntry]:
        """兼容旧接口：返回该 symbol 下任意一笔（若存在）。"""
        try:
            ids = self.client.smembers(self._symbol_index_key(symbol))
            for tid in ids:
                trade_json = self.client.hget(self.trade_hash_key, tid)
                if trade_json:
                    return TradeLedgerEntry.model_validate_json(trade_json)
            return None
        except redis.exceptions.RedisError as e:
            import logging as _logging
            _logging.getLogger(__name__).info(f"Error reading from Redis ledger for {symbol}: {e}")
            raise

    def get_all_trades(self) -> List[TradeLedgerEntry]:
        """获取台账中所有正在进行的交易。"""
        try:
            all_trades_raw = self.client.hgetall(self.trade_hash_key)
            if not all_trades_raw:
                return []
            return [
                TradeLedgerEntry.model_validate_json(trade_json)
                for trade_json in all_trades_raw.values()
            ]
        except redis.exceptions.RedisError as e:
            import logging as _logging
            _logging.getLogger(__name__).info(f"Error reading all trades from Redis ledger: {e}")
            raise

    def delete_trade(self, symbol: str) -> bool:
        """兼容旧接口：删除该 symbol 下任意一笔。"""
        try:
            ids = list(self.client.smembers(self._symbol_index_key(symbol)) or [])
            if not ids:
                return False
            # 删除第一笔
            tid = ids[0]
            self.client.hdel(self.trade_hash_key, tid)
            self.client.srem(self._symbol_index_key(symbol), tid)
            import logging as _logging
            _logging.getLogger(__name__).info(f"Ledger: Deleted trade {tid} for {symbol}")
            return True
        except redis.exceptions.RedisError as e:
            import logging as _logging
            _logging.getLogger(__name__).info(f"Error deleting from Redis ledger for {symbol}: {e}")
            raise

    # --- 新接口：按 trade_id 操作 ---
    def get_trade_by_id(self, trade_id: str) -> Optional[TradeLedgerEntry]:
        try:
            trade_json = self.client.hget(self.trade_hash_key, trade_id)
            if trade_json:
                return TradeLedgerEntry.model_validate_json(trade_json)
            return None
        except redis.exceptions.RedisError as e:
            import logging as _logging
            _logging.getLogger(__name__).info(f"Error reading trade_id {trade_id}: {e}")
            raise

    def delete_trade_by_id(self, trade_id: str) -> bool:
        try:
            trade = self.get_trade_by_id(trade_id)
            if not trade:
                return False
            removed = self.client.hdel(self.trade_hash_key, trade_id)
            self.client.srem(self._symbol_index_key(trade.symbol), trade_id)
            if removed:
                import logging as _logging
                _logging.getLogger(__name__).info(f"Ledger: Deleted trade {trade_id} for {trade.symbol}")
            return bool(removed)
        except redis.exceptions.RedisError as e:
            import logging as _logging
            _logging.getLogger(__name__).info(f"Error deleting trade_id {trade_id}: {e}")
            raise

    def get_trades_by_symbol(self, symbol: str) -> List[TradeLedgerEntry]:
        try:
            ids = self.client.smembers(self._symbol_index_key(symbol)) or []
            out: List[TradeLedgerEntry] = []
            for tid in ids:
                t = self.get_trade_by_id(tid)
                if t:
                    out.append(t)
            return out
        except redis.exceptions.RedisError as e:
            import logging as _logging
            _logging.getLogger(__name__).info(f"Error reading trades by symbol {symbol}: {e}")
            raise

    def get_all_active_symbols(self) -> List[str]:
        """获取所有需要被监控的交易的symbol列表。"""
        trades = self.get_all_trades()
        return [
            trade.symbol for trade in trades
            if trade.status in [TradeStatus.ACTIVE, TradeStatus.TP1_HIT]
        ]

    def update_trade_atomically(self, symbol: str, update_function) -> Optional[TradeLedgerEntry]:
        """
        提供一个原子性的更新操作，用于所有“先读后改再写”的场景。
        这可以防止并发冲突。

        :param symbol: 要更新的交易对
        :param update_function: 一个接收TradeLedgerEntry对象并返回修改后对象的函数
        :return: 更新后的TradeLedgerEntry对象，如果不存在则返回None
        """
        # 使用WATCH来确保在读写之间没有其他客户端修改这个哈希字段
        with self.client.pipeline() as pipe:
            try:
                # 兼容旧接口：取 symbol 下第一笔进行原子更新
                ids = list(self.client.smembers(self._symbol_index_key(symbol)) or [])
                if not ids:
                    return None
                trade_id = ids[0]
                pipe.watch(self.trade_hash_key)
                trade_json = pipe.hget(self.trade_hash_key, trade_id)
                if not trade_json:
                    return None

                trade = TradeLedgerEntry.model_validate_json(trade_json)
                
                # 调用传入的函数来执行修改逻辑
                updated_trade = update_function(trade)
                if not updated_trade: # 如果更新函数决定不更新，可以返回None
                    return trade
                    
                pipe.multi()
                pipe.hset(self.trade_hash_key, trade_id, updated_trade.model_dump_json())
                pipe.execute()
                
                import logging as _logging
                _logging.getLogger(__name__).info(f"Ledger: Atomically updated trade {trade_id} for {symbol}")
                return updated_trade
            except redis.exceptions.WatchError:
                # 如果在WATCH期间，哈希被修改了，操作会失败，可以进行重试
                import logging as _logging
                _logging.getLogger(__name__).info(f"WatchError on {symbol}, potential conflict. Retrying might be needed.")
                return None # 或者在这里加入重试逻辑
            except redis.exceptions.RedisError as e:
                import logging as _logging
                _logging.getLogger(__name__).info(f"Error during atomic update for {symbol}: {e}")
                raise

    def update_trade_by_id_atomically(self, trade_id: str, update_function) -> Optional[TradeLedgerEntry]:
        """按 trade_id 执行原子更新。"""
        with self.client.pipeline() as pipe:
            try:
                pipe.watch(self.trade_hash_key)
                trade_json = pipe.hget(self.trade_hash_key, trade_id)
                if not trade_json:
                    return None
                trade = TradeLedgerEntry.model_validate_json(trade_json)

                updated_trade = update_function(trade)
                if not updated_trade:
                    return trade

                pipe.multi()
                pipe.hset(self.trade_hash_key, trade_id, updated_trade.model_dump_json())
                pipe.execute()
                import logging as _logging
                _logging.getLogger(__name__).info(f"Ledger: Atomically updated trade {trade_id}")
                return updated_trade
            except redis.exceptions.WatchError:
                import logging as _logging
                _logging.getLogger(__name__).info(f"WatchError on trade_id={trade_id}, potential conflict. Retrying might be needed.")
                return None
            except redis.exceptions.RedisError as e:
                import logging as _logging
                _logging.getLogger(__name__).info(f"Error during atomic update for trade_id={trade_id}: {e}")
                raise

    # --- 辅助 ---
    def _symbol_index_key(self, symbol: str) -> str:
        return f"{self.symbol_index_prefix}{symbol}"

# --- 全局单例 ---
# 创建一个全局唯一的ledger实例，供应用其他部分导入和使用
# 这被称为“单例模式”，可以确保整个应用共享同一个数据库连接池
ledger_instance = TradeLedger(redis_url=settings.REDIS_URL)