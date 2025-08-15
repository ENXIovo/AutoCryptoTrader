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
        "description": "Fetch detailed account information for a specified cryptocurrency, including available balance, global trading funds data (e.g., margin, valuation, unrealized P&L), related trade history, and all open orders.",
        "parameters": {
            "type": "object",
            "properties": {
                "symbol": {
                    "type": "string",
                    "description": "Asset symbol, e.g., DOGE, ETH, BTC, TRUMP.",
                },
            },
            "required": ["symbol"],
            "additionalProperties": False,
        },
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
            "entry_price": {"type": "number", "description": "Entry price. For market orders, ignored."},
            "position_size": {"type": "number", "description": "Base asset size, e.g., 0.001."},
            "stop_loss_price": {"type": "number", "description": "Stop-loss trigger price."},
            "take_profits": {"type": "array", "description": "TP ladder (1–2 items). Percentages sum to 100.",
                "items": {"type": "object", "properties": {
                    "price": {"type": "number", "description": "TP price."},
                    "percentage_to_sell": {"type": "number", "minimum": 1, "maximum": 100, "description": "Sell percentage (1–100)."}
                }, "required": ["price", "percentage_to_sell"], "additionalProperties": False}
            },
            "entry_ordertype": {"type": "string", "enum": ["market", "limit"], "default": "market", "description": "Entry order type."},
            "post_only": {"type": "boolean", "description": "Post-only for limit orders (maker-only). Maps to Kraken oflags 'post'."},
            "userref": {"type": "integer", "description": "Optional user grouping tag. If omitted, executor will assign one."}
        },
        "required": ["symbol", "side", "entry_price", "position_size", "stop_loss_price", "take_profits"],
        "additionalProperties": False
    }
}

TOOL_SCHEMAS["amendOrder"] = {
    "type": "function",
    "name": "amendOrder",
    "description": "Amend an existing trade PRICES ONLY. Quantity/position_size cannot be amended. If order_id is provided, will attempt to amend the live exchange order (entry limit or stop-loss). If trade_id is provided, will amend ledger (stop-loss/TPs; entry price only when PENDING). To change size, first cancel (by order_id or trade_id) and then add a new order. Providing both identifiers is recommended to ensure one-shot consistency.",
    "parameters": {
        "type": "object",
        "properties": {
            "order_id": {"type": "string", "description": "Kraken order txid. Use entry order_id to change entry limit; use SL order_id to change stop-loss trigger."},
            "trade_id": {"type": "string", "description": "Internal trade identifier from ledger. Ensures ledger (SL/TPs) is updated even if exchange amend is not possible yet."},
            "new_entry_price": {"type": "number", "description": "New entry price (only for unfilled entry limit orders)."},
            "new_stop_loss_price": {"type": "number", "description": "New stop-loss trigger. If SL not created yet, updates ledger and will sync on creation."},
            "new_tp1_price": {"type": "number", "description": "New TP1 price (ledger only; strategy does not pre-place TP orders)."},
            "new_tp2_price": {"type": "number", "description": "New TP2 price (ledger only). If trade has only one TP, TP2 will NOT be auto-created."}
        },
        "required": [],
        "additionalProperties": False
    }
}

TOOL_SCHEMAS["cancelOrder"] = {
    "type": "function",
    "name": "cancelOrder",
    "description": "Cancel an order or an entire trade. With order_id, cancels that single live order (entry or SL) and, if it is the last open order (or SL with remaining_size=0), closes and deletes the ledger. With trade_id, cancels associated open orders and deletes the trade record.",
    "parameters": {
        "type": "object",
        "properties": {
            "order_id": {"type": "string", "description": "Kraken order txid to cancel (entry or stop-loss)."},
            "trade_id": {"type": "string", "description": "Ledger trade id. Will attempt to cancel associated open orders and delete the trade record."}
        },
        "required": [],
        "additionalProperties": False
    }
}
