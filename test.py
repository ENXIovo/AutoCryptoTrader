"""
test_api.py
-----------
简单测试本地运行的 GPT-Proxy：
1. 普通（非流式）接口调用
2. 流式接口调用，逐块打印文本
"""

import asyncio
import json
import httpx

BASE_URL = "http://localhost:8200/api/v1/generate-response"
HEADERS = {"Content-Type": "application/json"}


async def non_stream_test():
    """同步方式：一次性返回完整 JSON"""
    payload = {
        "message": "帮我总结一下今天比特币的大新闻",
        "tools": [{"type": "web_search_preview"}],   # 无工具就删掉此行
        "stream": False,
    }
    async with httpx.AsyncClient() as client:
        resp = await client.post(BASE_URL, headers=HEADERS, json=payload, timeout=None)
        resp.raise_for_status()
        data = resp.json()
        print("\n=== 非流式返回 ===")
        print(json.dumps(data, ensure_ascii=False, indent=2))


async def stream_test():
    """流式方式：边收边打印"""
    payload = {
        "message": "请帮我搜索并梳理整个泰国柬埔寨冲突的详细始末，要比新闻详细，是以国际关系深入研究的角度",
        "tools": [{"type": "web_search_preview"}],
        "stream": True,
    }
    async with httpx.AsyncClient() as client:
        async with client.stream("POST", BASE_URL, headers=HEADERS, json=payload, timeout=None) as resp:
            resp.raise_for_status()
            print("\n=== 流式返回 ===")
            async for chunk in resp.aiter_text():
                # 每行 chunk 结尾可能包含换行符，根据后端实现调整
                print(chunk, end="", flush=True)


if __name__ == "__main__":
    asyncio.run(non_stream_test())
    # asyncio.run(stream_test())
