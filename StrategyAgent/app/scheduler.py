import json
from .models import MessageRequest, MessageResponse
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
        # 1) 一开始，把所有可用工具 schema 注入
        req.tools = list(self.tool_schemas.values())
        req.tool_choice = "auto"

        # 2) 循环调用，直到没有工具调用
        resp: MessageResponse = self.gpt.send_message(req)
        
        # 3) 循环，直到没有自定义 function_call 为止
        while True:
            # 3.1) 只留下 type=="function_call" 的那部分
            custom_calls = [
                c for c in resp.tool_calls
                if c.get("type") == "function_call"
            ]
            if not custom_calls:
                break

            # 3.2) 执行这些自定义函数
            outputs = []
            for call in custom_calls:
                name = call["name"]
                if name not in self.tool_handlers:
                    raise RuntimeError(f"Unknown tool: {name}")
                args = json.loads(call["arguments"])
                result = self.tool_handlers[name](**args)
                outputs.append({
                    "type":    "function_call_output",
                    "call_id": call["call_id"],
                    "output":  json.dumps(result, ensure_ascii=False),
                })

            # 3.3) 构造下一轮请求，注意保留所有原始工具列表
            followup = MessageRequest(
                message               = req.message or "",
                session_id            = resp.session_id,
                previous_response_id  = resp.response_id,
                input                 = outputs,
                tools                 = req.tools,
                tool_choice           = req.tool_choice,
            )
            resp = self.gpt.send_message(followup)

        # 4) 跳出循环，返回最终由 GPT 生成的内容
        return resp.model_dump()
