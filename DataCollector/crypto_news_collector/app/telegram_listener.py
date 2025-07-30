# crypto_news_collector/app/telegram_listener.py
import asyncio
import logging

from telethon import TelegramClient, events

from app.config import settings
from app.db import SessionLocal
from app import crud

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


async def main():
    # 1) 启动客户端
    client = TelegramClient(
        settings.TELEGRAM_SESSION,
        settings.TELEGRAM_API_ID,
        settings.TELEGRAM_API_HASH,
    )
    await client.start()

    # 2) 解析监听频道列表
    channels: list = []
    for raw in settings.TELEGRAM_CHANNELS.split(","):
        ch = raw.strip()
        if not ch:
            continue
        channels.append(int(ch) if ch.lstrip("-+").isdigit() else ch)

    logger.info(f"Listening to channels: {channels}")

    # 3) 消息回调 —— 所有新消息一律入库（不做关键词过滤）
    @client.on(events.NewMessage(chats=channels))
    async def handler(event):
        text: str = event.message.message or ""
        source: str = event.chat.username or event.chat.title or str(event.chat_id)

        session = SessionLocal()
        try:
            crud.save_news_event(
                session,
                {
                    "symbol": None,          # 后续可做 NLP 抽取币种
                    "source": source,
                    "raw_text": text,
                },
            )
            snippet = text.replace("\n", " ")[:80]
            logger.info(f"Saved news from {source}: {snippet}")
        finally:
            session.close()

    # 4) 进入阻塞循环直至手动中断
    await client.run_until_disconnected()


if __name__ == "__main__":
    asyncio.run(main())
