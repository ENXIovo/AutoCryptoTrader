import time
import uuid
import logging
import json
import asyncio
from typing import Dict, Any, Optional, List

import redis
from fastapi import FastAPI, HTTPException

from app.config import settings
from app.virtual_exchange import virtual_exch

logger = logging.getLogger(__name__)
app = FastAPI(title="Virtual Exchange (Hyperliquid-Lite)")

_redis_client = redis.Redis.from_url(settings.REDIS_URL, decode_responses=True)

# ---------- Models (Simplified) ----------
# No pydantic models needed for strict validation for now,
# just raw dicts to mimic Hyperliquid's JSON-RPC style bodies.

# ---------- API Endpoints ----------

@app.post("/exchange/order")
async def place_order(order: Dict[str, Any]):
    """
    Hyperliquid-style Order Placement
    Payload: {
        "coin": "BTC", 
        "is_buy": true, 
        "sz": 0.1, 
        "limit_px": 90000, 
        "order_type": {"limit": {"tif": "Gtc"}}, 
        "reduce_only": false
    }
    """
    try:
        # Adapt to VirtualExchange internal logic (which we kept compatible for now)
        # VirtualExchange uses: pair, type(buy/sell), ordertype(market/limit), volume, price
        
        coin = order.get("coin")
        is_buy = order.get("is_buy")
        sz = float(order.get("sz") or 0.0)
        limit_px = float(order.get("limit_px") or 0.0)
        order_type_obj = order.get("order_type", {})
        
        # Map fields
        pair = f"{coin}USDT" if coin else "XBTUSDT" # Defaulting for now if coin is raw
        if coin == "XBT" or coin == "BTC": pair = "XBTUSDT"
        if coin == "ETH": pair = "ETHUSDT"
        
        side = "buy" if is_buy else "sell"
        
        # Determine ordertype
        if "market" in order_type_obj:
            ordertype = "market"
            price = None
        else:
            ordertype = "limit"
            price = limit_px
            
        # Call VirtualExchange synchronously (Memory Lock is fast enough)
        # We reuse the existing 'add_order' method but construct the internal dict it expects
        internal_payload = {
            "pair": pair,
            "type": side,
            "ordertype": ordertype,
            "volume": sz,
            "price": price,
            "userref": int(time.time()) # Auto-generate userref
        }
        
        result = await virtual_exch.add_order(internal_payload)
        
        if result.get("error"):
            return {"status": "err", "response": str(result["error"])}
            
        txid = result["result"]["txid"][0]
        
        # Hyperliquid returns: {"status": "ok", "response": {"type": "order", "data": {"oid": ...}}}
        return {
            "status": "ok",
            "response": {
                "type": "order",
                "data": {"oid": txid}
            }
        }
    except Exception as e:
        logger.error(f"Order placement failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/exchange/cancel")
async def cancel_order(req: Dict[str, Any]):
    """
    Payload: {"coin": "BTC", "oid": "txid_string"}
    """
    try:
        txid = req.get("oid")
        result = await virtual_exch.cancel_order({"txid": txid})
        
        if result.get("error"):
             return {"status": "err", "response": str(result["error"])}

        return {
            "status": "ok",
            "response": {"type": "cancel", "data": {"statuses": ["success"]}}
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/info")
async def get_info(req: Dict[str, Any]):
    """
    Payload: {"type": "clearinghouseState", "user": "..."} (We ignore user for single-user mode)
    """
    req_type = req.get("type")
    
    if req_type == "metaAndAssetCtxs":
        # Return universe (prices)
        # We need to fetch latest prices from VirtualExchange's memory or Redis
        # This is used by Agent to see 'universe'
        return {
            "universe": [
                {"name": "BTC", "szDecimals": 5, "maxLeverage": 50},
                {"name": "ETH", "szDecimals": 4, "maxLeverage": 50}
            ]
        }
        
    if req_type == "clearinghouseState":
        # Return Balance and Positions
        balance = virtual_exch._balance
        total_equity = balance.get("USDT", 0.0) # Simplified
        
        # Construct positions list from Open Orders (VirtualExchange doesn't track positions yet, only orders)
        # M1 Simplified: We treat 'Orders' as the state.
        # Hyperliquid response structure:
        return {
            "marginSummary": {
                "accountValue": str(total_equity),
                "totalMarginUsed": "0.0"
            },
            "crossMarginSummary": {
                "accountValue": str(total_equity)
            },
            "assetPositions": [] # We don't track perp positions yet in M1
        }
        
    return {"status": "err", "response": "Unknown info type"}

# ---------- Background Tasks ----------

@app.on_event("startup")
async def startup_event():
    logger.info("Virtual Exchange (Hyperliquid-Lite) Started.")
    # Start the polling loop in background
    asyncio.create_task(market_data_polling_task())

async def market_data_polling_task():
    """
    Polls Redis for new 1m OHLC data every 60s and feeds VirtualExchange.
    """
    logger.info("[DRIVER] Starting Market Data Polling Task...")
    # TARGET_SYMBOLS = ["XBTUSDT", "ETHUSDT"] 
    # Read from settings if available, else default
    targets = settings.TARGET_SYMBOLS or ["XBTUSDT"]
    
    while True:
        try:
            for symbol in targets:
                key = f"gpt_data:{symbol}"
                data_json = _redis_client.get(key)
                if not data_json: continue
                
                data = json.loads(data_json)
                k1m = data.get("intervals_data", {}).get("1")
                if not k1m: continue
                
                o = k1m.get("open")
                h = k1m.get("high")
                l = k1m.get("low")
                c = k1m.get("close")
                
                if o is not None:
                    virtual_exch.on_kline_update(symbol, o, h, l, c)
            
            await asyncio.sleep(60)
        except Exception as e:
            logger.error(f"Polling error: {e}")
            await asyncio.sleep(10)
