# scripts/create_session.py  (SAFE)
import os
from pathlib import Path
from telethon import TelegramClient

API_ID = int(os.environ["TELEGRAM_API_ID"])
API_HASH = os.environ["TELEGRAM_API_HASH"]

SESSION_NAME = os.environ.get("TELEGRAM_SESSION_NAME", "").strip()
if not SESSION_NAME:
    raise SystemExit("Set TELEGRAM_SESSION_NAME explicitly (no default).")

session_dir = Path(os.environ.get("TELEGRAM_SESSION_DIR", "sessions"))
session_dir.mkdir(parents=True, exist_ok=True)

SESSION_PATH = str(session_dir / f"{SESSION_NAME}.session")

client = TelegramClient(SESSION_PATH, API_ID, API_HASH)

async def main():
    await client.start()
    me = await client.get_me()
    print("✅ Logged in as:", me.username or me.first_name)
    await client.disconnect()

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
