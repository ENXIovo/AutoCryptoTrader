from telethon import TelegramClient
import asyncio
api_id = 23624041
api_hash = "ff514248e705f200306f10dd7905b00a"
session_name = "news_session"  # 保证和 config.py 一致

client = TelegramClient(session_name, api_id, api_hash)

async def main():
    await client.start()
    print("✅ 已成功生成 session 文件")

if __name__ == "__main__":
    asyncio.run(main())
