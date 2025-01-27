import redis.asyncio as redis
import json
from datetime import datetime
from fastapi import HTTPException, status
from schemas.chat_schemas import ChatSession, ChatMessage
from config import (
    REDIS_HOST,
    REDIS_PORT,
    REDIS_DB,
    REDIS_PASSWORD
)

class DateTimeEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, datetime):
            return obj.isoformat()
        return super().default(obj)


class RedisStore:
    _instance = None

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super(RedisStore, cls).__new__(cls, *args, **kwargs)
        return cls._instance

    def __init__(self):
        if not hasattr(self, 'initialized'):  # 防止重复初始化
            # 使用配置变量代替硬编码值
            self.redis_client = redis.from_url(
                f"redis://{REDIS_HOST}:{REDIS_PORT}/{REDIS_DB}?encoding=utf-8&password={REDIS_PASSWORD}"
            )
            self.initialized = True

    async def close(self):
        """Close the Redis connection pool."""
        await self.redis_client.aclose()

    async def save_session(self, session):
        # 保存会话信息
        await self.save_session_info(session)
        
        # 保存系统消息
        await self.save_system_message(session.session_id, session.system_message)
        
        # 保存用户和助手消息
        await self.save_messages(session.session_id, session.messages)

    async def save_session_info(self, session):
        try:
            session_info_key = f"session:info:{session.session_id}"
            session_info = session.model_dump(include={"session_id", "created_at", "current_model", "context_length", "temperature"})
            session_info = {k: v.isoformat() if isinstance(v, datetime) else v for k, v in session_info.items()}
            await self.redis_client.hset(session_info_key, mapping=session_info)
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Error saving session info: {str(e)}"
            )

    async def save_system_message(self, session_id, system_message):
        try:
            system_message_key = f"session:system_message:{session_id}"
            system_message_info = system_message.model_dump()
            system_message_info = {k: v.isoformat() if isinstance(v, datetime) else v for k, v in system_message_info.items()}
            await self.redis_client.hset(system_message_key, mapping=system_message_info)
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Error saving system message: {str(e)}"
            )

    async def save_messages(self, session_id, messages):
        try:
            messages_key = f"session:messages:{session_id}"
            for message in messages:
                score = message.created_at.timestamp()
                message_json = message.model_dump_json()
                await self.redis_client.zadd(messages_key, {message_json: score})
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Error saving chat messages: {str(e)}"
            )

    async def get_session(self, session_id):
        """Retrieve session data from Redis."""
        session_info_key = f"session:info:{session_id}"
        system_message_key = f"session:system_message:{session_id}"
        messages_key = f"session:messages:{session_id}"
        
        try:
            session_info = await self.redis_client.hgetall(session_info_key)
            session_info = {k.decode("utf-8"): v.decode("utf-8") for k, v in session_info.items()}
            if not session_info:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found in Redis.")
            
            # 对日期时间字符串进行转换
            if 'created_at' in session_info:
                session_info['created_at'] = datetime.fromisoformat(session_info['created_at'])
            
            session = ChatSession(**session_info)

            system_message_info = await self.redis_client.hgetall(system_message_key)
            system_message_info = {k.decode("utf-8"): v.decode("utf-8") for k, v in system_message_info.items()}

            if 'created_at' in system_message_info:
                system_message_info['created_at'] = datetime.fromisoformat(system_message_info['created_at'])
            session.system_message = ChatMessage(**system_message_info)
            
            messages_scores = await self.redis_client.zrange(messages_key, 0, -1, withscores=True)
            messages = [ChatMessage.model_validate_json(msg) for msg, _ in messages_scores] if messages_scores else []
            session.messages = messages

            return session
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Error retrieving session from Redis: {repr(e)}",
            )
        
    async def save_token_usage(self, stream_name: str, token_data: dict, maxlen=10000):
        """将token使用情况保存到Redis Stream中"""
        try:
            await self.redis_client.xadd(stream_name, token_data, maxlen=maxlen, approximate=True)
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Error saving token usage to Redis Stream: {str(e)}"
            )
    