# completion_handler.py
import asyncio
import json
import tiktoken
import datetime
from services.session_manager import SessionManager
from apis.api_manager_factory import APIManagerFactory
from config import (
    DEFAULT_SYSTEM_MESSAGE,
    DEFAULT_CONTEXT_LENGTH,
    DEFAULT_TEMPERATURE,
    DEFAULT_DEPLOYMENT_NAME,
)


async def handle_user_message(request, user, session_manager: SessionManager):
    """Main function to handle the user message flow."""
    session = await prepare_session(request, user, session_manager)

    # 调用 API 生成并添加助手消息
    api_manager = APIManagerFactory.get_api_manager(session.current_model)
    merged_response = await api_manager.generate_response(session)

    merged_response["response_data"]["username"] = user
    merged_response["response_data"]["model"] = session.current_model

    session_manager.add_message_to_session(
        "assistant", session, json.dumps(merged_response["ai_message"])
    )

    # 并行执行保存会话和计费数据操作
    await asyncio.gather(
        session_manager.save_session(session),
        session_manager.save_billing_data(merged_response["response_data"]),
    )

    return {"session_id": session.session_id, "content": merged_response["ai_message"]}


async def handle_user_message_stream(request, user, session_manager: SessionManager):
    """Main function to handle the user message flow with streaming."""
    session = await prepare_session(request, user, session_manager)

    # 调用 API 生成并添加助手消息
    api_manager = APIManagerFactory.get_api_manager(session.current_model)
    stream_generator = api_manager.generate_response_stream(session)

    content_buffer = []
    async for chunk in stream_generator: 
        content_buffer.append(chunk)
        yield chunk

    # 初始化 tiktoken 编码器
    encoder = tiktoken.encoding_for_model(session.current_model)

    # 获取完整响应内容以便后续保存
    full_response = "".join(content_buffer)
    prompt_tokens = encoder.encode(
        "".join(
            [msg["content"] for msg in api_manager.prepare_request(session)["input"]]
        )
    )
    completion_tokens = encoder.encode(full_response)
    received_at = int(datetime.datetime.now().timestamp())

    merged_response = {
        "ai_message": full_response,
        "response_data": {
            "prompt_tokens": len(prompt_tokens),
            "completion_tokens": len(completion_tokens),
            "created_at": int(session.created_at.timestamp()),
            "received_at": received_at,
        },
    }

    # 更新和保存会话
    session_manager.add_message_to_session("assistant", session, full_response)

    merged_response["response_data"]["username"] = user
    merged_response["response_data"]["model"] = session.current_model

    await asyncio.gather(
        session_manager.save_session(session),
        session_manager.save_billing_data(merged_response["response_data"]),
    )


async def prepare_session(request, user, session_manager: SessionManager):
    """Helper function to prepare session and other details."""
    session_id = request.get("session_id")
    session = await session_manager.get_session(session_id) if session_id else None

    system_message = request.get("system_message")
    context_length = request.get("context_length")
    current_model = request.get("deployment_name")

    if system_message is None:
        if session:
            system_message = session.system_message
        else:
            system_message = DEFAULT_SYSTEM_MESSAGE
    if context_length is None:
        if session:
            context_length = session.context_length
        else:
            context_length = DEFAULT_CONTEXT_LENGTH
    if current_model is None:
        if session:
            current_model = session.current_model
        else:
            current_model = DEFAULT_DEPLOYMENT_NAME
    
    if not session:
        session = session_manager.create_new_session(
            system_message, context_length, current_model
        )
    else:
        session_manager.update_session(
            session, system_message, context_length, current_model
        )

    if request.get("tools") is not None:
        session.tool_config = {
            "tools": request["tools"],
            "tool_choice": request.get("tool_choice", "auto"),
        }

    session_manager.add_message_to_session("user", session, request.get("message"))

    return session
