from __future__ import annotations

import os
import re
import asyncio
from datetime import datetime
from pathlib import Path

from telethon import TelegramClient, events
from sqlalchemy.exc import IntegrityError

from app.db.session import SessionLocal
from app.models import Channel, Call

BASE58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
CA_REGEX = re.compile(rf"(?<![{BASE58}])([{BASE58}]{{32,44}})(?:pump)?(?![{BASE58}])")


def extract_first_solana_ca(text: str) -> str | None:
    if not text:
        return None
    m = CA_REGEX.search(text)
    return m.group(1) if m else None


TELEGRAM_API_ID = int(os.environ["TELEGRAM_API_ID"])
TELEGRAM_API_HASH = os.environ["TELEGRAM_API_HASH"]

# Prefer explicit TELEGRAM_SESSION_FILE if you ever want to override it.
# Otherwise build from TELEGRAM_SESSION / TELEGRAM_SESSION_NAME and store inside /app/sessions (mounted volume).
SESSION_DIR = Path(os.environ.get("TELEGRAM_SESSION_DIR", "/app/sessions"))
SESSION_DIR.mkdir(parents=True, exist_ok=True)

SESSION_NAME = (
    os.environ.get("TELEGRAM_SESSION")
    or os.environ.get("TELEGRAM_SESSION_NAME")
    or "tg_lab_session"
)

DEFAULT_SESSION_FILE = str(SESSION_DIR / f"{SESSION_NAME}.session")
SESSION_PATH = os.environ.get("TELEGRAM_SESSION_FILE", DEFAULT_SESSION_FILE)

client = TelegramClient(SESSION_PATH, TELEGRAM_API_ID, TELEGRAM_API_HASH)


async def main():
    print(f"[LISTENER] running | session={SESSION_PATH}")

    db = SessionLocal()
    try:
        channels = db.query(Channel).filter(Channel.enabled == True).all()  # noqa: E712
    finally:
        db.close()

    if not channels:
        print("[LISTENER] No enabled channels in DB. Add via API: POST /channels")
        await client.start()
        await client.run_until_disconnected()
        return

    for ch in channels:
        username = ch.telegram_username
        print(f"[LISTENER] subscribe @{username} (channel_id={ch.id})")

        async def handler(event, channel_id=ch.id):
            msg = (event.message.message or "").strip()
            mint = extract_first_solana_ca(msg)
            if not mint:
                return

            db = SessionLocal()
            try:
                call = Call(
                    channel_id=channel_id,
                    mint=mint,
                    symbol=mint[:6],
                    status="RECORDING",
                    duration_sec=int(os.getenv("RECORD_DURATION_SEC", "1500")),
                )
                db.add(call)
                db.commit()
                print(
                    f"[CALL] channel_id={channel_id} mint={mint[:8]}... at "
                    f"{datetime.now().isoformat(timespec='seconds')}"
                )
            except IntegrityError:
                db.rollback()
                # already seen for that channel → ignore
            finally:
                db.close()

        client.add_event_handler(handler, events.NewMessage(chats=username))

    await client.start()
    await client.run_until_disconnected()


if __name__ == "__main__":
    asyncio.run(main())
