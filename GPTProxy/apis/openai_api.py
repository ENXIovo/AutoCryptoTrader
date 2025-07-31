import datetime
import openai
from openai import AsyncOpenAI
from typing import Dict, List, AsyncGenerator
from schemas.chat_schemas import ChatSession, ChatMessage
from apis.api_manager import APIManager
from fastapi import HTTPException, status
from config import DEFAULT_INPUT_FIELDS

# 请求生成：SessionManager调用APIManager，传递必要的信息（如用户消息和会话上下文）。
# 与OpenAI交互：APIManager构建并发送请求到OpenAI API，然后等待并处理响应。
# 处理响应：APIManager接收OpenAI的响应，并从中提取或生成回复消息。
# 返回数据：APIManager将生成的消息返回给SessionManager。


# Subclass of APIManager to handle OpenAI API responses
class OpenAIAPI(APIManager):
    def __init__(self, client: AsyncOpenAI):
        self.client = client
        self.input_fields = DEFAULT_INPUT_FIELDS
        # self.encoder = tiktoken.encoding_for_model(model_name)

    def prepare_request(self, session: ChatSession) -> Dict:
        """
        Prepare the data for the OpenAI API request.
        """
        data = {
            "model": session.current_model,
            "input": self.format_input_messages(
                session.system_message, 
                session.get_context()
            )
        }

        # ★★ ① 统一从 session.tool_config 读取
        if session.tool_config.get("tools"):
            data["tools"] = session.tool_config["tools"]
            data["tool_choice"] = session.tool_config.get("tool_choice", "auto")
        print(data)
        return data

    def format_input_messages(
        self, system_message: ChatMessage, context: List[ChatMessage]
    ) -> list:
        # 生成最终的输入消息列表，包含 system_message 和根据需要调整的 recent_messages，以及 user_message
        return [
            system_message.model_dump(include=self.input_fields, exclude_none=True)
        ] + [
            m.model_dump(include=self.input_fields, exclude_none=True) for m in context
        ]

    def handle_response(self, response):
        if response.status == "failed" and response.error.get("code") == "content_filter":
            return {
                "ai_message": "Content was filtered due to inappropriate content. Please try again with different content.",
                "tool_calls": [],
                "response_data": {
                    "prompt_tokens": response.usage.prompt_tokens,
                    "completion_tokens": response.usage.completion_tokens,
                    "created_at": response.created_at.timestamp(),
                    "received_at": int(datetime.datetime.now().timestamp()),
                },
            }

        # 解析工具调用（统一格式）
        tool_calls = [
            item.model_dump()
            for item in response.output
            if item.type.endswith("_call")
        ]

        # 聚合 message 内容
        ai_message = ""
        for item in response.output:
            if item.type == "message":
                for part in item.content:
                    if part.type == "output_text":
                        ai_message += part.text

        return {
            "ai_message": ai_message,
            "tool_calls": tool_calls,
            "response_data": {
                "prompt_tokens": response.usage.input_tokens,
                "completion_tokens": response.usage.output_tokens,
                "created_at": response.created_at,
                "received_at": int(datetime.datetime.now().timestamp()),
            },
        }


    async def generate_response(self, session: ChatSession):
        """
        Generate a response from the OpenAI API (synchronous).
        """
        data = self.prepare_request(session)
        try:
            response = await self.client.responses.create(**data)
            return self.handle_response(response)
        except openai.OpenAIError as e:
            self.handle_openai_errors(e)


    def handle_openai_errors(self, e: openai.OpenAIError):
        """
        Handle OpenAI specific errors.
        """
        error_mapping = {
            openai.BadRequestError: (status.HTTP_400_BAD_REQUEST, "Invalid request: "),
            openai.RateLimitError: (status.HTTP_429_TOO_MANY_REQUESTS, "Rate limit exceeded: "),
            openai.APIConnectionError: (status.HTTP_503_SERVICE_UNAVAILABLE, "API connection error: "),
            openai.APITimeoutError: (status.HTTP_408_REQUEST_TIMEOUT, "API request timeout: "),
            openai.AuthenticationError: (status.HTTP_401_UNAUTHORIZED, "Authentication error: "),
            openai.ConflictError: (status.HTTP_409_CONFLICT, "Conflict error: "),
            openai.InternalServerError: (status.HTTP_500_INTERNAL_SERVER_ERROR, "Internal server error: "),
            openai.NotFoundError: (status.HTTP_404_NOT_FOUND, "Resource not found: "),
            openai.PermissionDeniedError: (status.HTTP_403_FORBIDDEN, "Permission denied: "),
            openai.UnprocessableEntityError: (status.HTTP_422_UNPROCESSABLE_ENTITY, "Unprocessable entity: "),
        }
        status_code, detail_prefix = error_mapping.get(type(e), (status.HTTP_500_INTERNAL_SERVER_ERROR, "Unexpected error: "))
        raise HTTPException(status_code=status_code, detail=f"{detail_prefix}{str(e)}")

    async def handle_stream_response(self, response) -> AsyncGenerator[dict, None]:
        """
        流式响应处理器，兼容文本 + function_call 的 tool calling。
        遵循 OpenAI 官方推荐的 event-based 聚合逻辑。
        """
        ai_text = ""
        final_tool_calls = {}  # output_index -> tool_call
        current_args = {}      # output_index -> str (arguments accumulating)

        async for event in response:
            # 文本 delta
            if event.type == "response.output_text.delta":
                ai_text += event.delta
                yield {"type": "text", "delta": event.delta}

            # 工具调用初始化
            elif event.type == "response.output_item.added" and event.item.type.endswith("_call"):
                final_tool_calls[event.output_index] = event.item
                current_args[event.output_index] = ""

            # 工具调用参数累积
            elif event.type == "response.function_call_arguments.delta":
                index = event.output_index
                if index in final_tool_calls:
                    current_args[index] += event.delta

            # 工具调用完成（一次 tool 调用完整组装好）
            elif event.type == "response.function_call_arguments.done":
                index = event.output_index
                tool_call = final_tool_calls[index]
                tool_call.arguments = current_args[index]
                yield {"type": "tool_call", "call": tool_call.model_dump()}

            # 最终收尾 + 补充 delta
            elif event.type == "response.completed":
                for item in event.response.output:
                    if item.type == "message":
                        for part in item.content:
                            if part.type == "output_text":
                                ai_text += part.text
                                yield {"type": "text", "delta": part.text}

    async def generate_response_stream(self, session: ChatSession) -> AsyncGenerator[str, None]:
        """
        Generate a response from the OpenAI API using streaming (synchronous).
        """
        data = self.prepare_request(session)
        try:
            response = await self.client.responses.create(**data, stream=True)
            async for text in self.handle_stream_response(response):
                yield text
        except openai.OpenAIError as e:
            self.handle_openai_errors(e)
