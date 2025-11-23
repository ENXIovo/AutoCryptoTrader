import asyncio
import json
import logging
from datetime import datetime, timezone

from telethon import TelegramClient, events
import redis

from .config import settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# Redis connection (sync client is sufficient here; xadd is fast)
redis_client = redis.Redis.from_url(settings.REDIS_URL)

async def main():
    client = TelegramClient(settings.TELEGRAM_SESSION, settings.TELEGRAM_API_ID, settings.TELEGRAM_API_HASH)
    await client.start()

    # Parse configured channels (IDs or @usernames)
    channels = []
    for raw in settings.TELEGRAM_CHANNELS.split(","):
        ch = raw.strip()
        if ch:
            channels.append(int(ch) if ch.lstrip("-+").isdigit() else ch)

    logger.info(f"Listening to Telegram channels: {channels}")

    @client.on(events.NewMessage(chats=channels))
    async def handler(event):
        text = event.message.message or ""
        if not text.strip():
            # skip empty messages
            return

        source = event.chat.username or event.chat.title or str(event.chat_id)
        ts = str(datetime.now(timezone.utc).timestamp())  # Unix时间戳（字符串）

        # payload fields for Redis stream
        fields = {
            "text": text,
            "source": source,
            "ts": ts,
            "chat_id": str(event.chat_id),
            "message_id": str(event.message.id),
        }

        try:
            # XADD to stream; use maxlen to auto-trim
            redis_client.xadd(
                settings.REDIS_STREAM_KEY,
                fields,
                maxlen=settings.REDIS_STREAM_MAXLEN,
                approximate=True
            )
            logger.info(f"Pushed message to stream from {source}")
        except Exception as exc:
            logger.exception(f"Failed to push message to Redis: {exc}")

    await client.run_until_disconnected()

if __name__ == "__main__":
    # Run the listener
    asyncio.run(main())
