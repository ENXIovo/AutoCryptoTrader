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
        ai_message = getattr(response, "output_text", "")
        tool_calls = [item for item in response.output if item.type.endswith("_call")]
        
        if tool_calls:
            print(f"本次响应共调用 {len(tool_calls)} 次工具：")
            for call in tool_calls:
                print(" -", call.type, call)

        if response.status == "failed" and response.error.get("code") == "content_filter":
            response_content = "Content was filtered due to inappropriate content. Please try again with different content."
        else:
            response_content = ai_message

        prompt_tokens = response.usage.input_tokens
        completion_tokens = response.usage.output_tokens
        received_at = int(datetime.datetime.now().timestamp())

        return {
            "ai_message": response_content,
            "response_data": {
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "created_at": response.created_at,
                "received_at": received_at,
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

    async def handle_stream_response(self, response) -> AsyncGenerator[str, None]:
        """
        Handle the streamed response from the OpenAI API.
        """
        async for chunk in response:
            if chunk.type.endswith("_call"):
                print("[TOOL]", chunk.type, "args/output:", chunk)
            
            # 实时文本增量 —— 适用于 gpt-4o、gpt-4.1 等主力模型
            elif chunk.type == "response.output_text.delta":
                yield chunk.delta

            # 少数模型（Deep-Research）仅把最终文本放在 completed
            elif chunk.type == "response.completed":
                for item in chunk.response.output:
                    if item.type == "message":
                        for part in item.content:
                            if part.type == "output_text":
                                yield part.text

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
