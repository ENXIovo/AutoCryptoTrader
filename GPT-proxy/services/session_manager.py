# session_manager.py
from schemas.chat_schemas import ChatSession, ChatMessage
from services.redis_store import RedisStore
from fastapi import HTTPException, status
from pydantic import ValidationError

class SessionManager:
    def __init__(self, redis_store: RedisStore):
        self.redis_store = redis_store

    def create_new_session(
        self,
        system_message: str,
        context_length: int,
        temperature: float,
        current_model: str,
    ) -> ChatSession:
        """Helper method to create a new ChatSession."""
        try:
            return ChatSession(
                system_message=ChatMessage(role="system", content=system_message),
                context_length=context_length,
                temperature=temperature,
                current_model=current_model,
            )
        except ValidationError as e:
            # 处理 ValidationError
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=str(e)
            )

    async def get_session(self, session_id: str) -> ChatSession:
        """Retrieve an existing session based on session_id."""
        session = await self.redis_store.get_session(session_id)
        if session:
            return session
        else:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Session not found."
            )

    def add_message_to_session(self, role: str, session: ChatSession, prompt: str):
        """Add a message to the session and save the updated session."""
        if role not in ["user", "assistant"]:  # Validating role
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid role specified for message.",
            )

        new_message = ChatMessage(role=role, content=prompt)
        session.add_message(new_message)

    def update_session(self, session: ChatSession, system_message: str, context_length: int, temperature: float, current_model: str):
        try:
            if session.system_message != system_message:
                session.update_system_message(system_message)
            if session.context_length != context_length:
                session.context_length = context_length
            if session.temperature != temperature:
                session.temperature = temperature
            if session.current_model != current_model:
                session.current_model = current_model
        except ValidationError as e:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=str(e)
            )

    async def save_session(self, session: ChatSession):
        """Save the updated session."""
        await self.redis_store.save_session(session)

    async def save_billing_data(self, billing_data):

        # 使用RedisStore实例保存数据
        await self.redis_store.save_token_usage("billing_stream", billing_data)
