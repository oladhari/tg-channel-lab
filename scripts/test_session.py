# scripts/test_session.py
import os
import sys
from pathlib import Path
from telethon import TelegramClient

API_ID = int(os.environ["TELEGRAM_API_ID"])
API_HASH = os.environ["TELEGRAM_API_HASH"]

SESSION_DIR = Path(os.environ.get("TELEGRAM_SESSION_DIR", "/opt/tg-channel-lab/sessions"))
SESSION_DIR.mkdir(parents=True, exist_ok=True)

name = sys.argv[1] if len(sys.argv) > 1 else ""
if not name:
    raise SystemExit("Usage: python scripts/test_session.py <session_name_without_.session>")

session_path = str(SESSION_DIR / f"{name}.session")

client = TelegramClient(session_path, API_ID, API_HASH)

async def main():
    await client.connect()
    if not await client.is_user_authorized():
        print("❌ NOT authorized:", session_path)
        return
    me = await client.get_me()
    print("✅ OK:", session_path)
    print("   user:", me.username or me.first_name, "| id:", me.id)
    await client.disconnect()

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
