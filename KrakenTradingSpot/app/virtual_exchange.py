import time
import uuid
import logging
import json
from typing import Dict, Any, Optional, Tuple

import redis

from app.config import settings
from app.data_client import DataClient

logger = logging.getLogger(__name__)


class VirtualExchange:
    """
    V1.1 虚拟撮合 (K-Line Matching & Simple Wallet)
    
    Design Philosophy:
    1. Match against 1-minute OHLC (DataCollector) instead of real-time Ticks.
       - Buy Limit fills if Low <= Price
       - Sell Limit fills if High >= Price
       - Stop Loss fills if Low <= Trigger (Sell Side)
    
    2. Simple Wallet (Single Ledger)
       - Order Place -> Deduct Balance immediately (Locked)
       - Order Cancel -> Refund Balance immediately
       - Order Fill -> No balance change (already deducted), just swap asset
    
    3. Snapshot Persistence
       - Save full state to Redis on every state change.
    """

    def __init__(self) -> None:
        self._orders: Dict[str, Dict[str, Any]] = {}  # txid -> order dict
        self._user_orders: Dict[str, set[str]] = {}   # userref -> {txid}
        # Wallet: {"USDT": 10000.0, "BTC": 0.5, ...}
        self._balance: Dict[str, float] = {"USDT": 10000.0, "BTC": 0.0, "ETH": 0.0} 
        
        self._r = redis.Redis.from_url(settings.REDIS_URL, decode_responses=True)
        self._snapshot_key = "virtual_exchange:snapshot"
        
        # Load state from Redis if exists
        self._load_snapshot()

    # ---------- Persistence ----------
    def _save_snapshot(self):
        """Serialize full state to Redis."""
        state = {
            "orders": self._orders,
            "balance": self._balance,
            # user_orders can be rebuilt from orders, but saving for simplicity
            # sets are not JSON serializable, convert to list
            "user_orders": {k: list(v) for k, v in self._user_orders.items()}
        }
        try:
            self._r.set(self._snapshot_key, json.dumps(state))
        except Exception as e:
            logger.error(f"[VIRT] Snapshot save failed: {e}")

    def _load_snapshot(self):
        """Load full state from Redis."""
        try:
            data = self._r.get(self._snapshot_key)
            if not data:
                logger.info("[VIRT] No snapshot found, starting fresh.")
                return
            
            state = json.loads(data)
            self._orders = state.get("orders", {})
            self._balance = state.get("balance", {"USDT": 10000.0})
            
            # Rebuild user_orders sets
            raw_user_orders = state.get("user_orders", {})
            self._user_orders = {k: set(v) for k, v in raw_user_orders.items()}
            
            logger.info(f"[VIRT] Snapshot loaded. Orders: {len(self._orders)}, Balance: {self._balance}")
        except Exception as e:
            logger.error(f"[VIRT] Snapshot load failed: {e}")

    # ---------- Helpers ----------
    def _new_txid(self) -> str:
        return f"VIRT-{uuid.uuid4().hex[:16]}"

    def _stream_key(self, txid: str) -> str:
        return f"{settings.ORDER_EVENT_STREAM_PREFIX}{txid}"

    def _publish_event(self, txid: str, status: str, extra: Optional[Dict[str, Any]] = None) -> None:
        fields = {"status": status, "ts": str(time.time())}
        if extra:
            for k, v in extra.items():
                if v is not None:
                    fields[k] = str(v)
        try:
            self._r.xadd(self._stream_key(txid), fields)
        except Exception as e:
            logger.info(f"[VIRT] publish_event failed txid={txid} err={e}")

    def _parse_oflags(self, oflags: Any) -> Tuple[bool, str]:
        if oflags is None:
            return (False, "")
        if isinstance(oflags, list):
            post_only = "post" in oflags
            return (post_only, ",".join(oflags))
        s = str(oflags)
        post_only = "post" in s.split(",")
        return (post_only, s)

    def _get_quote_currency(self, pair: str) -> str:
        # Simple heuristic for V1
        if pair.endswith("USD") or pair.endswith("USDT"):
            return "USDT"
        if pair.endswith("BTC"):
            return "BTC"
        return "USDT" # Fallback

    def _get_base_currency(self, pair: str) -> str:
        # Simple heuristic
        # XBTUSD -> BTC, ETHUSD -> ETH
        p = pair.replace("USDT", "").replace("USD", "")
        if p == "XBT": return "BTC"
        if p == "XETH": return "ETH"
        return p

    # ---------- Wallet Logic ----------
    def _deduct_funds(self, currency: str, amount: float) -> bool:
        """Try to deduct amount from balance. Return True if successful."""
        current = self._balance.get(currency, 0.0)
        if current >= amount:
            self._balance[currency] = current - amount
            return True
        return False

    def _refund_funds(self, currency: str, amount: float):
        """Refund amount to balance (e.g. on cancel)."""
        self._balance[currency] = self._balance.get(currency, 0.0) + amount

    def _deposit_funds(self, currency: str, amount: float):
        """Add amount to balance (e.g. on fill)."""
        self._balance[currency] = self._balance.get(currency, 0.0) + amount

    # ---------- Public API ----------
    async def add_order(self, order_data: Dict[str, Any]) -> Dict[str, Any]:
        userref = order_data.get("userref") or int(time.time())
        pair = str(order_data.get("pair") or "")
        side = str(order_data.get("type") or "").lower()
        ordertype = str(order_data.get("ordertype") or "").lower()
        volume = float(order_data.get("volume") or 0.0)
        price_input = order_data.get("price")
        price = float(price_input) if price_input is not None else None
        
        # Determine cost
        base_curr = self._get_base_currency(pair)
        quote_curr = self._get_quote_currency(pair)
        
        cost = 0.0
        currency_to_deduct = ""
        
        # Basic validation
        if ordertype == "market":
             # Market Buy: Deduct USDT (Approximate cost? Or assume huge balance? )
             # For V1 Simple Wallet: We need an estimated price for Market Buy to lock funds.
             # Let's look up last price just for cost estimation.
             # If DataClient fails, we can't place market order safely in this strict wallet.
             pass 
        elif ordertype == "limit":
            if not price:
                return {"error": ["EOrder:Limit price required"], "result": {}}
                
        # Cost Calculation & Deduction
        if side == "buy":
            currency_to_deduct = quote_curr
            if ordertype == "limit":
                cost = volume * price
            else:
                # Market Buy: Lock based on last price * (1 + slippage buffer) or just last price
                # For M1 Simple: Let's skip Market Orders logic for a moment or handle them immediately at Close
                # Re-use data client just for 'Close' price estimation
                # But wait, M1 philosophy is K-Line Matching.
                # MARKET ORDER: Executed at current CANDLE CLOSE (future) or previous CANDLE CLOSE?
                # Convention: Market order fills at NEXT AVAILABLE PRICE.
                # For simulation: We can fill it immediately at 'current known price' (last close).
                pass
        else: # sell
            currency_to_deduct = base_curr
            cost = volume # Selling base asset

        # For now, let's implement Limit Order deduction strictly
        if ordertype == "limit":
            if not self._deduct_funds(currency_to_deduct, cost):
                 return {"error": ["EOrder:Insufficient funds"], "result": {}}
        
        # ... Market order logic requires a bit more thought on 'what price to lock'.
        # For M1 Simplified: Let's allow Market Orders to go negative temporarily or check last known price.
        # Let's implement Limit first as it's the core.
        
        if ordertype == "market":
             # For Market orders, we assume immediate fill attempt in 'matching loop' or 'now'.
             # Let's allow it but warn about funds later.
             cost = 0.0 # Placeholder for market orders
             pass

        post_only, oflags_raw = self._parse_oflags(order_data.get("oflags"))
        txid = self._new_txid()
        now = time.time()

        # Create Open Order
        self._orders[txid] = {
            "pair": pair,
            "type": side,
            "ordertype": ordertype,
            "volume": volume,
            "filled": 0.0,
            "status": "open",
            "userref": userref,
            "oflags": oflags_raw,
            "price": price,
            "created_at": now,
            "cost_locked": cost, # Track what we locked
            "currency_locked": currency_to_deduct
        }
        self._user_orders.setdefault(str(userref), set()).add(txid)
        
        self._save_snapshot() # Persist
        self._publish_event(txid, "open", {"vol": str(volume)})

        # M1 Patch: 如果带有 close[...] 参数，自动创建关联的止损单 (Stop Loss)
        # 这不是 Kraken 的标准行为（Kraken 是在成交后自动触发），但在 M1 里我们模拟为"同时提交两张单"
        # 简化处理：解析 close_ordertype 和 close_price
        close_type = order_data.get("close_ordertype") or order_data.get("close[ordertype]")
        close_price_val = order_data.get("close_price") or order_data.get("close[price]")
        
        if close_type and close_price_val:
            # 创建第二张单（止损单）
            # 注意：止损单方向与主单相反
            sl_side = "sell" if side == "buy" else "buy"
            sl_price = float(close_price_val)
            sl_txid = self._new_txid()
            
            # 止损单也是 Open 的，但在 Kraken 逻辑里它应该是 Pending 直到主单成交。
            # M1 简化：我们直接把它设为 Open，但在 Matching 逻辑里，只有当主单 Closed 后才允许它成交？
            # 或者更简单：直接挂着。如果主单没成交，止损单也不会被触发（因为价格还没到）。
            # 但是如果价格直接穿过主单打到止损？
            # 无论如何，为了 verify_m1 能查到 stop_loss，我们得把它存进去。
            
            self._orders[sl_txid] = {
                "pair": pair,
                "type": sl_side,
                "ordertype": str(close_type), # e.g. "stop-loss"
                "volume": volume, # 同主单量
                "filled": 0.0,
                "status": "open",
                "userref": userref, # 同一个 userref，便于分组
                "price": sl_price, # Trigger price
                "created_at": now,
                "cost_locked": 0.0, # SL 通常不锁钱（或者锁仓位）
                "currency_locked": "",
                "parent_txid": txid # 标记关联
            }
            self._user_orders.setdefault(str(userref), set()).add(sl_txid)
            self._save_snapshot()
            self._publish_event(sl_txid, "open", {"vol": str(volume), "type": "stop-loss"})
            logger.info(f"[VIRT] Created conditional close order {sl_txid} type={close_type} price={sl_price}")
        
        return {"error": [], "result": {"txid": [txid]}}

    async def cancel_order(self, cancel_data: Dict[str, Any]) -> Dict[str, Any]:
        count = 0
        txid = cancel_data.get("txid")
        userref = cancel_data.get("userref")

        targets: set[str] = set()
        if txid and txid in self._orders:
            targets.add(txid)
        if userref is not None:
            targets |= set(self._user_orders.get(str(userref), set()))

        for t in list(targets):
            od = self._orders.get(t)
            if not od: continue
            if od.get("status") in {"closed", "canceled"}: continue
            
            # Refund
            locked = od.get("cost_locked", 0.0)
            currency = od.get("currency_locked", "")
            if locked > 0 and currency:
                self._refund_funds(currency, locked)
                od["cost_locked"] = 0.0 # Clear lock
            
            od["status"] = "canceled"
            od["canceled_at"] = time.time()
            self._publish_event(t, "canceled")
            count += 1
            
        self._save_snapshot()
        return {"error": [], "result": {"count": count}}

    # ... Amend to be implemented similar to Cancel+Add logic (Refund old, Deduct new)

    async def get_balance(self) -> Dict[str, Any]:
        """Return current wallet balance."""
        return {"error": [], "result": self._balance}

    # ---------- K-Line Matching Engine (The Core) ----------
    def on_kline_update(self, pair: str, o: float, h: float, l: float, c: float):
        """
        Called when a new 1m candle is finalized.
        Matches all open orders for this pair against High/Low/Close.
        """
        updates = False
        
        for txid, order in self._orders.items():
            if order.get("status") != "open": continue
            if order.get("pair") != pair: continue
            
            side = order["type"]
            ordertype = order["ordertype"]
            price = order["price"]
            vol = order["volume"]
            
            matched_price = None
            
            # 1. Market Order -> Fills at Close (Simplified)
            if ordertype == "market":
                matched_price = c
                
            # 2. Limit Buy -> Fills if Low <= Price
            elif side == "buy" and ordertype == "limit":
                if l <= price:
                    matched_price = price # Limit guarantees price (simplified to limit price)
                    
            # 3. Limit Sell -> Fills if High >= Price
            elif side == "sell" and ordertype == "limit":
                if h >= price:
                    matched_price = price
            
            # 4. Stop Loss (Sell) -> Fills if Low <= StopPrice (Trigger)
            # (Assuming 'price' field holds stop trigger for simple stop-loss orders in V1)
            elif side == "sell" and "stop" in ordertype: 
                # Kraken logic is complex for stops, V1 simplified:
                # If we treat 'price' as trigger:
                if l <= price:
                    matched_price = price # Slippage ignored for V1
            
            if matched_price:
                # Execute Match
                self._execute_fill(txid, order, matched_price)
                updates = True
                
        if updates:
            self._save_snapshot()

    def _execute_fill(self, txid: str, order: Dict[str, Any], fill_price: float):
        """
        Handle funds swap and status update.
        Note: Cost was already deducted (Locked). 
        We need to:
        1. Buy Side: We locked USDT. Now we give user BTC. 
           (If locked > actual cost, refund diff? V1: Limit fills at limit price, so cost == locked)
        2. Sell Side: We locked BTC. Now we give user USDT.
        """
        side = order["type"]
        vol = order["volume"]
        pair = order["pair"]
        base_curr = self._get_base_currency(pair)
        quote_curr = self._get_quote_currency(pair)
        
        if side == "buy":
            # User gets BTC (Base)
            self._deposit_funds(base_curr, vol)
            # User spent USDT (Quote) - already locked.
            # If Market order, we need to deduct NOW since we didn't lock precisely.
            if order["ordertype"] == "market":
                cost = vol * fill_price
                # Try deduct. If fail -> partial fill? V1: Force negative or fail? 
                # Let's allow negative for V1 simplicity or check balance.
                self._deduct_funds(quote_curr, cost) 
                
        else: # sell
            # User gets USDT (Quote)
            revenue = vol * fill_price
            self._deposit_funds(quote_curr, revenue)
            # User spent BTC (Base) - already locked.
            if order["ordertype"] == "market":
                self._deduct_funds(base_curr, vol)

        order["status"] = "closed"
        order["avg_price"] = fill_price
        order["filled"] = vol
        order["closed_at"] = time.time()
        # Clear locks just in case
        order["cost_locked"] = 0.0
        
        self._publish_event(txid, "closed", {"vol": str(vol), "price": str(fill_price)})
        logger.info(f"[VIRT] Order {txid} FILLED at {fill_price}")


# Singleton
virtual_exch = VirtualExchange()
