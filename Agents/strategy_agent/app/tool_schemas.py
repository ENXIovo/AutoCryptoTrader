from typing import Dict, Any

# 函数 schema 给 GPT-Proxy 使用
TOOL_SCHEMAS: Dict[str, Dict[str, Any]] = {
    "calcRRR": {
        "type": "function",
        "name": "calcRRR",
        "description": "Pure-math RRR calculator. Inputs: entry, stop, tp1, tp2 (optional). Returns risk/reward and RRRs. No policy.",
        "parameters": {
        "type": "object",
        "properties": {
            "cases": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                "entry": { "type": "number" },
                "stop":  { "type": "number" },
                "tp1":   { "type": "number" },
                "tp2":   { "type": "number" }
                },
                "required": ["entry","stop","tp1"],
                "additionalProperties": False
            }
            }
        },
        "required": ["cases"],
        "additionalProperties": False
        }
    },
    "getTopNews": {
        "type": "function",
        "name": "getTopNews",
        "description": "Retrieve a ranked list of top cryptocurrency news items from all TTL buckets, ordered by relevance score.",
        "parameters": { "type": "object", "properties": {}, "additionalProperties": False }
    },
    "web_search_preview": {
        "type": "web_search_preview"
    },
    "getAccountInfo": {
        "type": "function",
        "name": "getAccountInfo",
        "description": "Fetch full Kraken-filter snapshot: balances, trade balance, open orders (with userref), and trade history.",
        "parameters": { "type": "object", "properties": {}, "additionalProperties": False },
    },
    "getKlineIndicators": {
        "type": "function",
        "name": "getKlineIndicators",
        "description": "Fetch the most recent multi-timeframe (1m, 5m, 15m, 1h, 4h, 1d) candlestick data and related technical indicators (MACD, RSI, SMA, Bollinger Bands, etc.) for a given trading pair.",
        "parameters": {
            "type": "object",
            "properties": {
                "symbol": {
                    "type": "string",
                    "description": "Kraken-supported trading pair, e.g., DOGEUSD, ETHUSD, BTCUSD, TRUMPUSD.",
                },
            },
            "required": ["symbol"],
            "additionalProperties": False,
        },
    },
}

# ---- Meeting reschedule tool (CTO only) ----
TOOL_SCHEMAS["rescheduleMeeting"] = {
    "type": "function",
    "name": "rescheduleMeeting",
    "description": (
        "Schedule a one-off strategy meeting to run after a short countdown (in minutes). "
        "This only overrides the NEXT meeting. Regardless of calling this tool or not, "
        "the system will still run at a fixed 4-hour cadence at minute 05 UTC each day."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "countdown_minutes": {
                "type": "integer",
                "minimum": 5,
                "maximum": 180,
                "description": "Countdown window in minutes (5–180)."
            },
            "reason": {
                "type": "string",
                "description": "Brief reason for requesting an earlier or delayed next meeting."
            }
        },
        "required": ["countdown_minutes", "reason"],
        "additionalProperties": False
    }
}

# ---- Append trading tools (stream pushers for KrakenTradingSpot) ----
TOOL_SCHEMAS["addOrder"] = {
    "type": "function",
    "name": "addOrder",
    "description": "Create a new trade plan (spot only) and enqueue it to the trading stream for execution by KrakenTradingSpot.",
    "parameters": {
        "type": "object",
        "properties": {
            "symbol": {"type": "string", "description": "Kraken altname, e.g., XBTUSD, ETHUSD."},
            "side": {"type": "string", "enum": ["buy", "sell"], "description": "Order side."},
            "entry_price": {"oneOf": [
                {"type": "number"},
                {"type": "string", "description": "Supports Kraken relative formats like '+5' or '+1.5%'."}
            ], "description": "Entry price (absolute number or relative string). For market orders, ignored."},
            "position_size": {"type": "number", "description": "Base asset size, e.g., 0.001."},
            "stop_loss_price": {"type": "number", "description": "Stop-loss trigger price."},
            "take_profits": {"type": "array", "description": "TP ladder (1–2 items). Percentages sum to 100.",
                "items": {"type": "object", "properties": {
                    "price": {"type": "number", "description": "TP price."},
                    "percentage_to_sell": {"type": "number", "minimum": 1, "maximum": 100, "description": "Sell percentage (1–100)."}
                }, "required": ["price", "percentage_to_sell"], "additionalProperties": False}
            },
            "entry_ordertype": {"type": "string", "enum": [
                "market",
                "limit",
                "stop-loss",
                "take-profit",
                "stop-loss-limit",
                "take-profit-limit",
                "trailing-stop",
                "trailing-stop-limit"
            ], "default": "market", "description": "Entry order type (Kraken spot)."},
            "entry_price2": {"oneOf": [
                {"type": "number"},
                {"type": "string", "description": "Supports Kraken relative formats like '+0' or '+0.5%'."}
            ], "description": "Secondary price for *-limit or trailing-limit styles (Kraken price2)."},
            "trigger": {"type": "string", "enum": ["index", "last"], "description": "Trigger source for conditional orders (Kraken trigger)."},
            "timeinforce": {"type": "string", "enum": ["GTC", "IOC", "GTD"], "description": "Time-in-force policy."},
            "oflags": {"type": "array", "items": {"type": "string"}, "description": "Kraken order flags array (e.g., ['post']). Will be serialized and forwarded."},
            "post_only": {"type": "boolean", "description": "Convenience flag. When true, adds 'post' to oflags (maker-only)."}
        },
        "required": ["symbol", "side", "entry_price", "position_size", "stop_loss_price", "take_profits"],
        "additionalProperties": False
    }
}

TOOL_SCHEMAS["amendOrder"] = {
    "type": "function",
    "name": "amendOrder",
    "description": "Amend existing orders by userref (PRICES ONLY). Quantity/position_size cannot be amended. Use only userref to update: entry limit (if still unfilled), stop-loss trigger, and TP prices (ledger-only). To change size, first cancel (by userref) and then add a new order.",
    "parameters": {
        "type": "object",
        "properties": {
            "userref": {"type": "integer", "description": "Group identifier to amend orders and ledger (no exposure of order_id/trade_id)."},
            "new_entry_price": {"type": "number", "description": "New entry price (only for unfilled entry limit orders)."},
            "new_stop_loss_price": {"type": "number", "description": "New stop-loss trigger. If SL not created yet, updates ledger and will sync on creation."},
            "new_tp1_price": {"type": "number", "description": "New TP1 price (ledger only; strategy does not pre-place TP orders)."},
            "new_tp2_price": {"type": "number", "description": "New TP2 price (ledger only). If trade has only one TP, TP2 will NOT be auto-created."}
        },
        "required": ["userref"],
        "additionalProperties": False
    }
}

TOOL_SCHEMAS["cancelOrder"] = {
    "type": "function",
    "name": "cancelOrder",
    "description": "Cancel a whole set of orders and delete the ledger by userref only. Do not expose order_id/trade_id.",
    "parameters": {
        "type": "object",
        "properties": {
            "userref": {"type": "integer", "description": "Group identifier to cancel the whole set on exchange and delete ledger (no exposure of order_id/trade_id)."}
        },
        "required": ["userref"],
        "additionalProperties": False
    }
}
