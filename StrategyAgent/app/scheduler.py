import json
from .models import MessageRequest, MessageResponse, ToolCall
from .gpt_client import GPTClient
from typing import Any, Callable, Dict

class Scheduler:
    """
    核心编排：两阶段 function calling，完全与具体工具解耦。
    """
    def __init__(
        self,
        gpt_client: GPTClient,
        tool_handlers: Dict[str, Callable[..., Any]],
        tool_schemas: Dict[str, Dict[str, Any]],
    ):
        self.gpt = gpt_client
        self.tool_handlers = tool_handlers
        self.tool_schemas = tool_schemas

    def analyze(self, req: MessageRequest) -> dict:
        # 注入可用工具 schema
        req.tools = list(self.tool_schemas.values())
        req.tool_choice = "auto"

        # 第一次发给 GPT
        first_resp: MessageResponse = self.gpt.send_message(req)

        # 若无工具调用，直接返回
        if not first_resp.tool_calls:
            return first_resp.model_dump()

        # 取第一个调用，执行 handler
        call: ToolCall = first_resp.tool_calls[0]
        name = call.name
        args = json.loads(call.arguments)
        if name not in self.tool_handlers:
            raise RuntimeError(f"Unknown tool called: {name}")
        result = self.tool_handlers[name](**args)

        # 构造 function_call_output 回传
        followup_req = MessageRequest(
            message    = req.message or "",
            session_id           = first_resp.session_id,
            previous_response_id = first_resp.response_id,
            input                = [{
                "type":    "function_call_output",
                "call_id": call.call_id,
                "output":  json.dumps(result, ensure_ascii=False),
            }],
            tools                = list(self.tool_schemas.values()),
            tool_choice          = "auto",
        )
        second_resp: MessageResponse = self.gpt.send_message(followup_req)
        return second_resp.model_dump()
