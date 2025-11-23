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
        "description": "Fetch account information from the virtual exchange: balances, margin summary, and open orders (with oid). Returns clearinghouse state including account value and current positions.",
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

TOOL_SCHEMAS["placeOrder"] = {
    "type": "function",
    "name": "placeOrder",
    "description": "Place a new order on the virtual exchange with required stop-loss and take-profit orders (OCO format). Supports market orders (limit_px=0) and limit orders. Returns order ID (oid) for tracking. When either SL or TP triggers, the other will be automatically cancelled.",
    "parameters": {
        "type": "object",
        "properties": {
            "coin": {
                "type": "string",
                "description": "Trading pair base asset, e.g., 'BTC', 'ETH', 'XBT'. The system will automatically append 'USDT' to form the pair."
            },
            "is_buy": {
                "type": "boolean",
                "description": "True for buy orders, false for sell orders."
            },
            "sz": {
                "type": "number",
                "description": "Order size in base asset units, e.g., 0.1 BTC."
            },
            "limit_px": {
                "type": "number",
                "description": "Limit price. Set to 0 for market orders. For limit orders, specify the desired execution price."
            },
            "stop_loss": {
                "type": "object",
                "description": "Required stop-loss order configuration. OCO: if this triggers, take-profit will be cancelled.",
                "properties": {
                    "price": {
                        "type": "number",
                        "description": "Stop-loss trigger price. For buy orders, should be below entry price. For sell orders, should be above entry price."
                    }
                },
                "required": ["price"],
                "additionalProperties": False
            },
            "take_profit": {
                "type": "object",
                "description": "Required take-profit order configuration. OCO: if this triggers, stop-loss will be cancelled.",
                "properties": {
                    "price": {
                        "type": "number",
                        "description": "Take-profit trigger price. For buy orders, should be above entry price. For sell orders, should be below entry price."
                    }
                },
                "required": ["price"],
                "additionalProperties": False
            },
            "reduce_only": {
                "type": "boolean",
                "description": "If true, order can only reduce position size. Defaults to false.",
                "default": False
            }
        },
        "required": ["coin", "is_buy", "sz", "limit_px", "stop_loss", "take_profit"],
        "additionalProperties": False
    }
}

TOOL_SCHEMAS["cancelOrder"] = {
    "type": "function",
    "name": "cancelOrder",
    "description": "Cancel an existing order by order ID (oid). The oid is returned when placing an order via placeOrder.",
    "parameters": {
        "type": "object",
        "properties": {
            "coin": {
                "type": "string",
                "description": "Trading pair base asset, e.g., 'BTC', 'ETH', 'XBT'. Must match the coin used when placing the order."
            },
            "oid": {
                "type": "string",
                "description": "Order ID (transaction ID) returned from placeOrder. Use this to cancel the specific order."
            }
        },
        "required": ["coin", "oid"],
        "additionalProperties": False
    }
}
