"""
Hyperliquid SDK Client - 单职责：只负责封装 Hyperliquid SDK
提供 Info 和 Exchange 客户端的统一接口
"""
import logging
from typing import Optional, Dict, Any, List

import eth_account
from eth_account.signers.local import LocalAccount
from hyperliquid.exchange import Exchange
from hyperliquid.info import Info
from hyperliquid.utils import constants

from app.config import settings

logger = logging.getLogger(__name__)


class HyperliquidClient:
    """
    Hyperliquid SDK 客户端封装
    单职责：只负责与 Hyperliquid SDK 交互，不处理业务逻辑
    """
    
    def __init__(self):
        # 初始化账户
        self.account: LocalAccount = eth_account.Account.from_key(settings.HYPERLIQUID_SECRET_KEY)
        self.account_address = settings.HYPERLIQUID_ACCOUNT_ADDRESS
        if not self.account_address:
            self.account_address = self.account.address
        
        # 确定 API URL
        base_url = constants.TESTNET_API_URL if settings.HYPERLIQUID_TESTNET else constants.MAINNET_API_URL
        
        # 初始化 Info 和 Exchange
        self.info = Info(base_url, skip_ws=True)
        self.exchange = Exchange(
            self.account, 
            base_url, 
            account_address=self.account_address
        )
        
        logger.info(f"[HL Client] Initialized for address: {self.account_address} (testnet={settings.HYPERLIQUID_TESTNET})")
    
    def get_user_state(self) -> Dict[str, Any]:
        """获取用户状态（余额、持仓等）"""
        return self.info.user_state(self.account_address)
    
    def get_open_orders(self) -> List[Dict[str, Any]]:
        """获取未完成订单列表"""
        return self.info.open_orders(self.account_address)
    
    def query_order_by_oid(self, oid: int) -> Optional[Dict[str, Any]]:
        """根据订单ID查询订单状态"""
        return self.info.query_order_by_oid(self.account_address, oid)
    
    def get_meta(self) -> Dict[str, Any]:
        """获取 universe 元数据"""
        return self.info.meta()
    
    def place_order(
        self,
        coin: str,
        is_buy: bool,
        sz: float,
        limit_px: float,
        order_type: Dict[str, Any],
        reduce_only: bool = False,
        cloid: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        下单
        Returns: {"status": "ok", "response": {"data": {"statuses": [...]}}}
        """
        return self.exchange.order(coin, is_buy, sz, limit_px, order_type, reduce_only=reduce_only, cloid=cloid)
    
    def modify_order(
        self,
        oid: int,
        coin: str,
        is_buy: bool,
        sz: float,
        limit_px: float,
        order_type: Dict[str, Any],
        cloid: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        修改订单
        Returns: {"status": "ok", "response": {...}}
        """
        return self.exchange.modify_order(oid, coin, is_buy, sz, limit_px, order_type, cloid=cloid)
    
    def cancel_order(self, coin: str, oid: int) -> Dict[str, Any]:
        """
        取消订单
        Returns: {"status": "ok", "response": {...}}
        """
        return self.exchange.cancel(coin, oid)
    
    def bulk_orders(
        self,
        orders: List[Dict[str, Any]],
        grouping: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        批量下单（支持TPSL分组）
        grouping: "normalTpsl" for TPSL grouping
        Returns: {"status": "ok", "response": {"data": {"statuses": [...]}}}
        """
        return self.exchange.bulk_orders(orders, grouping=grouping)
    
    def update_leverage(
        self,
        leverage: int,
        coin: str,
        is_cross: bool = True
    ) -> Dict[str, Any]:
        """
        更新杠杆倍数
        leverage: 杠杆倍数（如 21 表示 21x）
        coin: 交易对（仅支持 perps）
        is_cross: True 为全仓，False 为逐仓
        Returns: {"status": "ok", "response": {...}}
        """
        return self.exchange.update_leverage(leverage, coin, is_cross)
    
    def update_isolated_margin(
        self,
        margin: float,
        coin: str
    ) -> Dict[str, Any]:
        """
        更新隔离保证金
        margin: 保证金金额（USD，可以为负数以减少保证金）
        coin: 交易对（仅支持 perps）
        Returns: {"status": "ok", "response": {...}}
        """
        return self.exchange.update_isolated_margin(margin, coin)


# Singleton
hl_client = HyperliquidClient()

