# scripts/make_buyer_session.py (CLEAN)
import os
from pathlib import Path
from telethon import TelegramClient

api_id = int(os.environ["TELEGRAM_API_ID"])
api_hash = os.environ["TELEGRAM_API_HASH"]

session_dir = Path(os.environ.get("TELEGRAM_SESSION_DIR", "/opt/tg-channel-lab/sessions"))
session_dir.mkdir(parents=True, exist_ok=True)

name = os.environ.get("TELEGRAM_SESSION_BUYER", "tg_lab_session_buyer").strip()
if not name:
    raise SystemExit("TELEGRAM_SESSION_BUYER is empty")

session_path = str(session_dir / f"{name}.session")

print("Creating buyer session:", session_path)
client = TelegramClient(session_path, api_id, api_hash)
client.start()
print("Saved:", session_path)
