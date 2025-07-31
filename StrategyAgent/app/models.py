from __future__ import annotations
from typing import Optional, List, Dict, Any
from pydantic import BaseModel


class MessageRequest(BaseModel):
    """
    请求发送给 GPT-Proxy 的消息体：
    - message: 本轮用户文本
    - session_id: 可选，上一次会话 ID
    - system_message, context_length, deployment_name, stream: 同 Proxy 定义
    - tools, tool_choice: 工具调用配置
    - previous_response_id: 用于 function_call_output 的上一次 GPT-Proxy 返回 ID
    - input: 用于 function_call_output 时传入上一次的输出
    """
    message: Optional[str] = None
    session_id: Optional[str] = None
    system_message: Optional[str] = None
    context_length: Optional[int] = None
    deployment_name: Optional[str] = None
    stream: Optional[bool] = False
    tools: Optional[List[Dict[str, Any]]] = None
    tool_choice: Optional[str] = "auto"
    previous_response_id: Optional[str] = None
    input: Optional[List[Dict[str, Any]]] = None

    def to_payload(self) -> dict:
        # 排除 None 字段，Pydantic v2 用 model_dump
        return self.model_dump(exclude_none=True)


class ToolCall(BaseModel):
    """
    GPT-Proxy 返回的工具调用结构：
    - id, call_id: 用于追踪调用
    - name: 函数名或工具名
    - arguments: 传给工具的 JSON 字符串
    - type, status: 可选字段，兼容内置调用
    """
    id: str
    call_id: str
    name: str
    arguments: str
    type: Optional[str] = None
    status: Optional[str] = None


class ResponseData(BaseModel):
    """
    GPT-Proxy 返回的计费/元数据：
    - prompt_tokens, completion_tokens
    - created_at, received_at: 时间戳（秒）
    """
    prompt_tokens: int
    completion_tokens: int
    created_at: int
    received_at: int


class MessageResponse(BaseModel):
    """
    从 GPT-Proxy 接收到的响应：
    - session_id: 对应会话
    - response_id: 本次生成的 ID（用于二次调用）
    - content: 模型生成的文本
    - tool_calls: 本次触发的所有工具调用
    - response_data: 计费与时间信息
    """
    session_id: str
    response_id: Optional[str] = None
    content: Optional[str] = None
    tool_calls: Optional[List[ToolCall]] = []
    response_data: Optional[ResponseData] = None
