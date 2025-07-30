import datetime
import openai
import sys
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
    def __init__(self, client):
        self.client = client
        self.input_fields = DEFAULT_INPUT_FIELDS
        # self.encoder = tiktoken.encoding_for_model(model_name)

    def prepare_request(self, session: ChatSession) -> Dict:
        """
        Prepare the data for the OpenAI API request.
        """
        message_list = self.format_input_messages(
            session.system_message, session.get_context()
        )
        print(message_list)
        return {
            "model": session.current_model,
            "messages": message_list,
            "temperature": session.temperature,
        }

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
        ai_message = response.choices[0].message.content
        finish_reason = response.choices[0].finish_reason

        if finish_reason == "content_filter":
            response_content = "Content was filtered due to inappropriate content. Please try again with different content."
        else:
            response_content = ai_message

        prompt_tokens = response.usage.prompt_tokens
        completion_tokens = response.usage.completion_tokens
        received_at = int(datetime.datetime.now().timestamp())

        return {
            "ai_message": response_content,
            "response_data": {
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "created_at": response.created,
                "received_at": received_at,
            },
        }

    def generate_response(self, session: ChatSession):
        """
        Generate a response from the OpenAI API (synchronous).
        """
        data = self.prepare_request(session)
        try:
            response = self.client.chat.completions.create(**data)
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

    async def handle_stream_response(self, response: AsyncGenerator) -> AsyncGenerator[str, None]:
        """
        Handle the streamed response from the OpenAI API.
        """
        async for chunk in response:
            if not chunk.choices:
                continue

            delta = chunk.choices[0].delta

            # Check if 'finish_reason' is available in the 'choices' list
            if chunk.choices[0].finish_reason:
                break
            delta_content = delta.content if delta and delta.content is not None else ""
            if delta_content:
                yield delta_content

    def generate_response_stream(self, session: ChatSession):
        """
        Generate a response from the OpenAI API using streaming (synchronous).
        """
        data = self.prepare_request(session)
        try:
            response = self.client.chat.completions.create(**data, stream=True)
            for chunk in response:
                if chunk.choices and chunk.choices[0].delta.content is not None:
                    yield chunk.choices[0].delta.content
        except openai.OpenAIError as e:
            self.handle_openai_errors(e)
