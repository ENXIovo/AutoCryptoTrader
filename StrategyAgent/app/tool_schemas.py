from typing import Dict, Any

# 函数 schema 给 GPT-Proxy 使用
TOOL_SCHEMAS: Dict[str, Dict[str, Any]] = {
    "latest_news": {
        "type": "function",
        "name": "latest_news",
        "description": "Fetch the latest crypto news events",
        "parameters": {
            "type": "object",
            "properties": {
                "limit":   {"type":"integer","description":"Number of items","minimum":1,"maximum":500},
                "channel": {"type":["string","null"],"description":"Filter by source channel"},
                "keyword": {"type":["string","null"],"description":"Keyword filter on text"},
            },
            "required": ["limit"],
            "additionalProperties": False
        }
    },
    "web_search_preview": {
        "type": "web_search_preview"
    },
    "kraken_filter": {
        "type": "function",
        "name": "kraken_filter",
        "description": "获取账户中特定币种的余额、挂单和可交易金额等信息",
        "parameters": {
            "type": "object",
            "properties": {
                "symbol": {
                    "type": "string",
                    "description": "币种符号，例如 DOGE, ETH, BTC, TRUMP 等",
                },
            },
            "required": ["symbol"],
            "additionalProperties": False,
        },
    },
    "gpt_latest": {
        "type": "function",
        "name": "gpt_latest",
        "description": "获取某币种最近一分钟内的K线数据及技术指标（MACD、RSI、SMA、布林带等）",
        "parameters": {
            "type": "object",
            "properties": {
                "symbol": {
                    "type": "string",
                    "description": "币种符号，例如 DOGE, ETH, BTC, TRUMP 等",
                },
            },
            "required": ["symbol"],
            "additionalProperties": False,
        },
    },

}
