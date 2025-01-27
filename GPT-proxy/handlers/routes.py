# handlers/routes.py
# import tracemalloc
from fastapi import APIRouter, Depends, Request
from schemas.chat_schemas import MessageRequest
from handlers.completion_handler import handle_user_message, handle_user_message_stream
from services.session_manager import SessionManager
from fastapi.responses import StreamingResponse, JSONResponse

router = APIRouter(prefix="/v1")


# 依赖项函数，从应用状态获取session_manager
async def get_session_manager_from_app_state(request: Request):
    return request.app.state.session_manager


# 接收消息并生成响应
@router.post("/generate-response")
async def process_message(
    request: MessageRequest,
    session_manager: SessionManager = Depends(get_session_manager_from_app_state),
    user: str = "Michael",
):
    if request.stream:
        stream_generator = handle_user_message_stream(
            request.dict(exclude_none=True, exclude_unset=True), user, session_manager
        )
        return StreamingResponse(stream_generator, media_type="text/plain")
    else:
        response = await handle_user_message(
            request.dict(exclude_none=True, exclude_unset=True), user, session_manager
        )
        return JSONResponse(response)
