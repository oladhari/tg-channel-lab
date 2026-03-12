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

CHANNEL_RELOAD_SEC = int(os.getenv("LISTENER_CHANNEL_RELOAD_SEC", "60"))


def extract_first_solana_ca(text: str) -> str | None:
    if not text:
        return None
    m = CA_REGEX.search(text)
    return m.group(1) if m else None


TELEGRAM_API_ID = int(os.environ["TELEGRAM_API_ID"])
TELEGRAM_API_HASH = os.environ["TELEGRAM_API_HASH"]

SESSION_DIR = Path(os.environ.get("TELEGRAM_SESSION_DIR", "/app/sessions"))
SESSION_DIR.mkdir(parents=True, exist_ok=True)

LISTENER_SESSION_NAME = os.environ.get("TELEGRAM_SESSION_LISTENER", "tg_lab_session_listener").strip()
if not LISTENER_SESSION_NAME:
    raise SystemExit("[LISTENER] TELEGRAM_SESSION_LISTENER is empty")

SESSION_PATH = str(SESSION_DIR / f"{LISTENER_SESSION_NAME}.session")
import fcntl
_lock_fp = open(SESSION_PATH + ".lock", "w")
try:
    fcntl.flock(_lock_fp, fcntl.LOCK_EX | fcntl.LOCK_NB)
except BlockingIOError:
    raise SystemExit(f"[LOCK] Session already in use: {SESSION_PATH}")
client = TelegramClient(SESSION_PATH, TELEGRAM_API_ID, TELEGRAM_API_HASH)


async def _subscribe_channel(ch: Channel, live_map: dict) -> bool:
    """Resolve and subscribe to a single channel. Returns True if subscribed."""
    username = (ch.telegram_username or "").strip().lstrip("@")
    if not username:
        print(f"[LISTENER] skip empty username (channel_id={ch.id})")
        return False

    try:
        entity = await client.get_input_entity(username)
    except (ValueError, UsernameNotOccupiedError, UsernameInvalidError) as e:
        print(f"[LISTENER] SKIP invalid username=@{username} (channel_id={ch.id}) -> {e}")
        return False
    except RPCError as e:
        print(f"[LISTENER] SKIP rpc error username=@{username} (channel_id={ch.id}) -> {e}")
        return False
    except Exception as e:
        print(f"[LISTENER] SKIP unexpected error username=@{username} (channel_id={ch.id}) -> {e}")
        return False

    channel_id = ch.id
    live_map[channel_id] = bool(ch.live_enabled)

    async def handler(event, channel_id=channel_id):
        msg = (event.message.message or "").strip()
        mint = extract_first_solana_ca(msg)
        if not mint:
            return

        db2 = SessionLocal()
        try:
            # Re-read live_enabled fresh from DB so it reflects latest UI setting
            ch_fresh = db2.query(Channel).filter(Channel.id == channel_id).one_or_none()
            live = bool(ch_fresh.live_enabled) if ch_fresh else False

            call = Call(
                channel_id=channel_id,
                mint=mint,
                symbol=mint[:6],
                status="RECORDING",
                duration_sec=int(os.getenv("RECORD_DURATION_SEC", "1500")),
                live_sell_enabled=live,
                live_buy_enabled=live,
                live_buy_status="NONE",
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

    client.add_event_handler(handler, events.NewMessage(chats=entity))
    print(f"[LISTENER] subscribe @{username} (channel_id={ch.id})")
    return True


async def _reload_channels(subscribed_ids: set, live_map: dict) -> None:
    """Check DB for newly enabled channels and subscribe to them."""
    db = SessionLocal()
    try:
        channels = db.query(Channel).filter(Channel.enabled == True).all()
    finally:
        db.close()

    new_channels = [c for c in channels if c.id not in subscribed_ids]
    if not new_channels:
        return

    print(f"[LISTENER] found {len(new_channels)} new channel(s) to subscribe")
    for ch in new_channels:
        ok = await _subscribe_channel(ch, live_map)
        if ok:
            subscribed_ids.add(ch.id)


async def main():
    print(f"[LISTENER] running | session={SESSION_PATH} | reload_interval={CHANNEL_RELOAD_SEC}s")

    await client.start()

    subscribed_ids: set = set()
    live_map: dict = {}

    # Initial subscription
    db = SessionLocal()
    try:
        channels = db.query(Channel).filter(Channel.enabled == True).all()
    finally:
        db.close()

    if not channels:
        print("[LISTENER] No enabled channels in DB. Add via UI — will auto-detect in 60s.")
    else:
        for ch in channels:
            ok = await _subscribe_channel(ch, live_map)
            if ok:
                subscribed_ids.add(ch.id)

    print(f"[LISTENER] ready | subscribed={len(subscribed_ids)}")

    # Background task: periodically reload channels added from UI
    async def reload_loop():
        while True:
            await asyncio.sleep(CHANNEL_RELOAD_SEC)
            try:
                await _reload_channels(subscribed_ids, live_map)
            except Exception as e:
                print(f"[LISTENER][RELOAD ERROR] {e}")

    asyncio.create_task(reload_loop())
    await client.run_until_disconnected()


if __name__ == "__main__":
    asyncio.run(main())
