# main.py

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
async def analyze_multi_agent_meeting():
    """
    新的端点，用于启动串行化的多代理会议流程。
    """
    try:
        # 直接 await 异步的会议函数
        result = await run_agents_in_sequence_async()
        return result
    except Exception as e:
        # 打印详细错误以便调试
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))