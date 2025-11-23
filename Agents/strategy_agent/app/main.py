# main.py

import json
from typing import Optional, Dict, Any
from fastapi import FastAPI, HTTPException
from .config import settings
from .models import MessageRequest, MessageResponse
from .gpt_client import GPTClient
from .tool_handlers import TOOL_HANDLERS
from .tool_schemas import TOOL_SCHEMAS
from .scheduler import Scheduler
# 导入新的串行会议运行器
from .agent_runner import run_agents_in_sequence_async

app = FastAPI()

# 单代理端点保持不变
scheduler = Scheduler(
    gpt_client=GPTClient(settings.gpt_proxy_url),
    tool_handlers=TOOL_HANDLERS,
    tool_schemas=TOOL_SCHEMAS,
)

@app.post("/analyze-gpt", response_model=MessageResponse)
def analyze_gpt(req: MessageRequest):
    try:
        return MessageResponse(**scheduler.analyze(req))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/analyze-multi-agent-meeting")
async def analyze_multi_agent_meeting(req: Optional[Dict[str, Any]] = None):
    """
    新的端点，用于启动串行化的多代理会议流程。
    
    支持回测模式：
    {
        "backtest_mode": true,
        "backtest_timestamp": 1705276800.0  // Unix秒
    }
    """
    try:
        backtest_timestamp = None
        if req and req.get("backtest_mode"):
            backtest_timestamp = req.get("backtest_timestamp")
            if backtest_timestamp is None:
                raise HTTPException(status_code=400, detail="backtest_timestamp is required when backtest_mode is true")
        
        # 直接 await 异步的会议函数
        result = await run_agents_in_sequence_async(backtest_timestamp=backtest_timestamp)
        return result
    except HTTPException:
        raise
    except Exception as e:
        # 打印详细错误以便调试
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/analyze")
async def analyze(req: Optional[Dict[str, Any]] = None):
    """
    回测模式接口（与/analyze-multi-agent-meeting相同，但名称更简洁）
    
    Payload:
    {
        "backtest_mode": true,  // 可选，默认false
        "backtest_timestamp": 1705276800.0  // 回测模式必需：Unix秒
    }
    """
    return await analyze_multi_agent_meeting(req)


@app.get("/results")
async def get_results(count: int = 10):
    """
    获取最近的会议结果
    """
    import redis
    from .config import settings
    
    try:
        r = redis.Redis.from_url(settings.redis_url, decode_responses=True)
        stream_key = settings.analysis_results_stream_key
        
        # 检查Stream是否存在
        try:
            stream_info = r.xinfo_stream(stream_key)
        except redis.exceptions.ResponseError:
            return {"error": f"Stream '{stream_key}' 不存在或为空", "count": 0, "results": []}
        
        # 读取最新的条目
        entries = r.xrevrange(stream_key, count=count)
        
        results = []
        for entry_id, fields in entries:
            try:
                payload = json.loads(fields.get("payload", "{}"))
                results.append({
                    "id": entry_id,
                    "timestamp": fields.get("ts", ""),
                    "data": payload
                })
            except json.JSONDecodeError:
                results.append({
                    "id": entry_id,
                    "timestamp": fields.get("ts", ""),
                    "data": {"error": "Failed to parse payload"}
                })
        
        return {
            "stream_key": stream_key,
            "total_length": stream_info.get("length", 0),
            "count": len(results),
            "results": results
        }
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))