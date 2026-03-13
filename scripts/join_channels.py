"""
Join all channels with the listener Telegram account.
Run once: docker compose run --rm listener python scripts/join_channels.py
"""
import os
import asyncio
from pathlib import Path
from telethon import TelegramClient
from telethon.tl.functions.channels import JoinChannelRequest
from telethon.errors import FloodWaitError

CHANNELS = [
    "bat_gamble",
    "mattprintalphacalls",
    "seekrtrending",
    "memesdontlies",
    "insightcasino",
    "pikachucallsgirls",
    "azunasplays",
    "memecoincallsignal",
    "zen_call",
    "minegems",
    "memecoinpumps300x",
    "kolsignal",
    "deezesignal",
    "earlybirdtg",
    "michiosuzukiofsatoshicalls",
    "marksgems",
    "alphakollswithins",
    "wesendingshit",
    "tradersviewtrenches",
    "marcellcooks",
    "alphakingsol",
    "mcdonald100xcalls",
    "cto_scanner",
    "michelleshills",
]

SESSION_DIR = Path(os.environ.get("TELEGRAM_SESSION_DIR", "/app/sessions"))
SESSION_NAME = os.environ.get("TELEGRAM_SESSION_LISTENER", "tg_lab_session_listener")
SESSION_PATH = str(SESSION_DIR / f"{SESSION_NAME}.session")

API_ID   = int(os.environ["TELEGRAM_API_ID"])
API_HASH = os.environ["TELEGRAM_API_HASH"]


async def main():
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
