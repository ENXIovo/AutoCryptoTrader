# chat_models.py
import datetime

from uuid import uuid4
from pydantic import BaseModel, Field
from typing import List, Dict, Optional, Any
from config import (
    DEFAULT_DEPLOYMENT_NAME,
    DEFAULT_CONTEXT_LENGTH,
    DEFAULT_SYSTEM_MESSAGE,
)


class MessageRequest(BaseModel):
    message: Optional[str] = None
    session_id: Optional[str] = None
    system_message: Optional[str] = None
    context_length: Optional[int] = None
    deployment_name: Optional[str] = None
    stream: Optional[bool] = False
    tools: Optional[List[Dict]] = None
    tool_choice: Optional[str] = "auto"
    previous_response_id: Optional[str] = None
    input: Optional[List[Dict[str, Any]]] = None

# 自定义的错误响应模型
class ErrorResponse(BaseModel):
    code: int
    message: str


def now_tz():
    # 获取当前的 UTC 时间
    return datetime.datetime.utcnow()


class ChatMessage(BaseModel):
    message_id: str = Field(default_factory=lambda: "M_" + str(uuid4()))
    role: str
    content: str
    created_at: datetime.datetime = Field(default_factory=now_tz)


class ChatSession(BaseModel):
    session_id: str = Field(default_factory=lambda: "S_" + str(uuid4()))
    system_message: ChatMessage = Field(
        default=ChatMessage(role="system", content=DEFAULT_SYSTEM_MESSAGE)
    )
    created_at: datetime.datetime = Field(default_factory=now_tz)
    current_model: str = Field(default=DEFAULT_DEPLOYMENT_NAME)
    messages: List[ChatMessage] = Field(default=[])
    context_length: int = Field(
        default=DEFAULT_CONTEXT_LENGTH,
        ge=0,
        error_messages={"ge": "context_length must be a non-negative integer"},
    )
    tool_config: dict = Field(default_factory=dict)

    def __init__(self, **data):
        super().__init__(**data)

    def add_message(self, message: ChatMessage) -> None:
        self.messages.append(message)

    def remove_message(self, message_id: str) -> None:
        self.messages = [m for m in self.messages if m.message_id != message_id]

    def get_context(self) -> List[ChatMessage]:
        # TODO: check token limit for specific model
        if isinstance(self.context_length, (int, float)):
            return self.messages[-int(self.context_length) - 1 :]
        else:
            raise TypeError(
                "context_length should be a number, but got {}".format(
                    type(self.context_length)
                )
            )

    def update_system_message(self, system_message: str):
        """Update the system message in the session."""
        self.system_message = ChatMessage(role="system", content=system_message)
