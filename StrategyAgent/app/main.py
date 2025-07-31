from fastapi import FastAPI, HTTPException
from .config import settings
from .models import MessageRequest, MessageResponse
from .gpt_client import GPTClient
from .tool_handlers import TOOL_HANDLERS
from .tool_schemas import TOOL_SCHEMAS
from .scheduler import Scheduler

app = FastAPI()

# 实例化依赖
gpt_client  = GPTClient(base_url=settings.gpt_proxy_url)
scheduler   = Scheduler(
    gpt_client    = gpt_client,
    tool_handlers = TOOL_HANDLERS,
    tool_schemas  = TOOL_SCHEMAS,
)

@app.post("/analyze-gpt", response_model=MessageResponse)
def analyze_gpt(req: MessageRequest):
    try:
        raw = scheduler.analyze(req)
        return MessageResponse(**raw)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
