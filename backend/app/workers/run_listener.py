# backend/app/workers/run_listener.py
from __future__ import annotations

import os
import re
import asyncio
from datetime import datetime
from pathlib import Path

from telethon import TelegramClient, events
from telethon.errors import UsernameNotOccupiedError, UsernameInvalidError
from telethon.errors.rpcerrorlist import RPCError

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

    # Load enabled channels + live map
    db = SessionLocal()
    try:
        channels = db.query(Channel).filter(Channel.enabled == True).all()
        live_map = {c.id: bool(c.live_enabled) for c in channels}
    finally:
        db.close()

    if not channels:
        print("[LISTENER] No enabled channels in DB. Add via API: POST /channels")
        await client.start()
        await client.run_until_disconnected()
        return

    await client.start()

    ok_count = 0
    skip_count = 0

    for ch in channels:
        username = (ch.telegram_username or "").strip().lstrip("@")
        if not username:
            print(f"[LISTENER] skip empty username (channel_id={ch.id})")
            skip_count += 1
            continue

        # Resolve entity once; if invalid, skip and do not crash
        try:
            entity = await client.get_input_entity(username)
        except (ValueError, UsernameNotOccupiedError, UsernameInvalidError) as e:
            print(f"[LISTENER] SKIP invalid username=@{username} (channel_id={ch.id}) -> {e}")
            skip_count += 1
            continue
        except RPCError as e:
            # Any other Telegram RPC errors (flood, etc.)
            print(f"[LISTENER] SKIP rpc error username=@{username} (channel_id={ch.id}) -> {e}")
            skip_count += 1
            continue
        except Exception as e:
            print(f"[LISTENER] SKIP unexpected error username=@{username} (channel_id={ch.id}) -> {e}")
            skip_count += 1
            continue

        print(f"[LISTENER] subscribe @{username} (channel_id={ch.id})")
        ok_count += 1

        async def handler(event, channel_id=ch.id):
            msg = (event.message.message or "").strip()
            mint = extract_first_solana_ca(msg)
            if not mint:
                return

            db2 = SessionLocal()
            try:
                call = Call(
                    channel_id=channel_id,
                    mint=mint,
                    symbol=mint[:6],
                    status="RECORDING",
                    duration_sec=int(os.getenv("RECORD_DURATION_SEC", "1500")),
                    live_sell_enabled=bool(live_map.get(channel_id, False)),
                )
                db2.add(call)
                db2.commit()
                print(
                    f"[CALL] channel_id={channel_id} mint={mint[:8]}... at "
                    f"{datetime.now().isoformat(timespec='seconds')}"
                )
            except IntegrityError:
                db2.rollback()
                # already seen for that channel → ignore
            finally:
                db2.close()

        # IMPORTANT: use resolved entity (not the string username)
        client.add_event_handler(handler, events.NewMessage(chats=entity))

    print(f"[LISTENER] ready | subscribed={ok_count} skipped={skip_count}")
    await client.run_until_disconnected()


if __name__ == "__main__":
    asyncio.run(main())
