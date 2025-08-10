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
