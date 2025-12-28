import os
from telethon import TelegramClient

API_ID = int(os.environ["TELEGRAM_API_ID"])
API_HASH = os.environ["TELEGRAM_API_HASH"]
SESSION_NAME = os.environ.get("TELEGRAM_SESSION_NAME", "tg_lab_session")
SESSION_PATH = os.path.join("sessions", SESSION_NAME)

client = TelegramClient(SESSION_PATH, API_ID, API_HASH)

async def main():
    await client.start()  # will prompt phone/code once
    me = await client.get_me()
    print("✅ Logged in as:", me.username or me.first_name)
    await client.disconnect()

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
