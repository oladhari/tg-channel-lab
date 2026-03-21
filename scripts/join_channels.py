"""
Join Telegram channels with the listener account so it can receive their messages.

Edit the CHANNELS list below (same usernames as in seed_channels.py), then run:

    docker compose run --rm listener python scripts/join_channels.py

The listener Telegram account must be a member of each channel to receive
NewMessage events. Run this once after adding channels.

Where to find channels: see scripts/seed_channels.py for tips.
"""
import os
import asyncio
from pathlib import Path
from telethon import TelegramClient
from telethon.tl.functions.channels import JoinChannelRequest
from telethon.errors import FloodWaitError

# Replace these with the usernames you want to join (without @)
CHANNELS: list[str] = [
    # "example_channel_username",
]

SESSION_DIR = Path(os.environ.get("TELEGRAM_SESSION_DIR", "/app/sessions"))
SESSION_NAME = os.environ.get("TELEGRAM_SESSION_LISTENER", "tg_lab_session_listener")
SESSION_PATH = str(SESSION_DIR / f"{SESSION_NAME}.session")

API_ID   = int(os.environ["TELEGRAM_API_ID"])
API_HASH = os.environ["TELEGRAM_API_HASH"]


async def main():
    if not CHANNELS:
        print("No channels configured. Edit the CHANNELS list in this file first.")
        return

    client = TelegramClient(SESSION_PATH, API_ID, API_HASH)
    await client.start()

    for username in CHANNELS:
        try:
            await client(JoinChannelRequest(username))
            print(f"✅ joined @{username}")
        except FloodWaitError as e:
            print(f"⏳ flood wait {e.seconds}s — sleeping...")
            await asyncio.sleep(e.seconds + 2)
            await client(JoinChannelRequest(username))
            print(f"✅ joined @{username} (after wait)")
        except Exception as e:
            print(f"❌ @{username} — {e}")
        await asyncio.sleep(2)  # small delay between joins to avoid flood

    await client.disconnect()
    print("Done.")


asyncio.run(main())
