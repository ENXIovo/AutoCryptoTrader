from typing import Dict, Any

# 函数 schema 给 GPT-Proxy 使用
TOOL_SCHEMAS: Dict[str, Dict[str, Any]] = {
    "getCryptoNews": {
        "type": "function",
        "name": "getCryptoNews",
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
    "getAccountInfo": {
        "type": "function",
        "name": "getAccountInfo",
        "description": "查询账户中与指定币种相关的资产信息，包括账户余额、全局交易资金信息（如保证金、估值、未实现盈亏）、该币种相关的交易历史记录，以及所有挂单",
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
    "getKlineIndicators": {
        "type": "function",
        "name": "getKlineIndicators",
        "description": "获取某币种在最近一分钟内更新的多周期（1m、5m、15m、1h、4h、1d）K线数据及其技术指标（包括 MACD、RSI、SMA、布林带等）",
        "parameters": {
            "type": "object",
            "properties": {
                "symbol": {
                    "type": "string",
                    "description": "kraken平台支持的交易对，例如 DOGEUSD, ETHUSD, BTCUSD, TRUMPUSD 等",
                },
            },
            "required": ["symbol"],
            "additionalProperties": False,
        },
    },

}
