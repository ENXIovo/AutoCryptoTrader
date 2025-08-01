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
}
