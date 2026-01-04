# backend/app/workers/run_trader_gmgn.py
from __future__ import annotations

import os
import time
import asyncio
from datetime import datetime, timezone
from pathlib import Path

from telethon import TelegramClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.models import Call, StrategyResult


GMGN_TARGET = os.getenv("GMGN_TARGET", "").strip()
GMGN_SELL_PERCENT = os.getenv("GMGN_SELL_PERCENT", "100%").strip()
LIVE_STRATEGY_KEY = os.getenv("LIVE_STRATEGY_KEY", "tp35_sl20").strip()
TRADER_POLL_SEC = int(os.getenv("TRADER_POLL_SEC", "5"))

# You have GMGN_COOLDOWN_SEC in .env but code used GMGN_SELL_COOLDOWN_SEC before
SELL_COOLDOWN_SEC = int(os.getenv("GMGN_SELL_COOLDOWN_SEC", os.getenv("GMGN_COOLDOWN_SEC", "45")))

TELEGRAM_API_ID = int(os.environ["TELEGRAM_API_ID"])
TELEGRAM_API_HASH = os.environ["TELEGRAM_API_HASH"]

# ✅ Session files are SQLite; DO NOT share same session between listener & trader
SESSION_DIR = Path(os.environ.get("TELEGRAM_SESSION_DIR", "/app/sessions"))
SESSION_DIR.mkdir(parents=True, exist_ok=True)

# Listener uses TELEGRAM_SESSION (existing)
# Trader uses TELEGRAM_SESSION_TRADER (new) -> separate file avoids sqlite "database is locked"
LISTENER_SESSION_NAME = (
    os.environ.get("TELEGRAM_SESSION")
    or os.environ.get("TELEGRAM_SESSION_NAME")
    or "tg_lab_session"
)

TRADER_SESSION_NAME = os.environ.get("TELEGRAM_SESSION_TRADER", f"{LISTENER_SESSION_NAME}_trader")

DEFAULT_SESSION_FILE = str(SESSION_DIR / f"{TRADER_SESSION_NAME}.session")
SESSION_PATH = os.environ.get("TELEGRAM_SESSION_FILE_TRADER", DEFAULT_SESSION_FILE)

client = TelegramClient(SESSION_PATH, TELEGRAM_API_ID, TELEGRAM_API_HASH)

_last_sent: dict[int, float] = {}  # call_id -> ts


async def gmgn_sell(mint: str) -> None:
    cmd = f"/sell {mint} {GMGN_SELL_PERCENT}"
    await client.send_message(GMGN_TARGET, cmd)


def pick_ready_calls(db: Session) -> list[tuple[Call, StrategyResult]]:
    c, sr = Call, StrategyResult
    stmt = (
        select(c, sr)
        .join(sr, sr.call_id == c.id)
        .where(c.status == "DONE")
        .where(c.live_sell_enabled == True)  # noqa
        .where(c.live_sell_status == "NONE")
        .where(sr.strategy_key == LIVE_STRATEGY_KEY)
        .order_by(c.started_at.asc())
        .limit(50)
    )
    return list(db.execute(stmt).all())


async def loop() -> None:
    if not GMGN_TARGET:
        raise SystemExit("GMGN_TARGET is empty. Set it in .env")

    print(
        f"[TRADER] starting | session={SESSION_PATH} | target={GMGN_TARGET} "
        f"| strategy={LIVE_STRATEGY_KEY} | poll={TRADER_POLL_SEC}s | cooldown={SELL_COOLDOWN_SEC}s"
    )

    # ✅ Do not prompt for login (docker has no TTY). Either session is authorized or fail clearly.
    await client.connect()
    if not await client.is_user_authorized():
        raise SystemExit(
            f"[TRADER] Telegram session not authorized: {SESSION_PATH}. "
            "Create it once interactively, then restart trader."
        )

    while True:
        db = SessionLocal()
        try:
            rows = pick_ready_calls(db)

            for call, sr in rows:
                now = time.time()
                last = _last_sent.get(call.id, 0.0)
                if now - last < SELL_COOLDOWN_SEC:
                    continue

                reason = (sr.outcome or "").upper()  # TP|SL|TIME
                try:
                    await gmgn_sell(call.mint)

                    call.live_sell_status = "SENT"
                    call.live_sell_reason = reason
                    call.live_sell_sent_at = datetime.now(timezone.utc)
                    call.live_sell_error = None

                    _last_sent[call.id] = now
                    db.add(call)
                    db.commit()

                    print(f"[TRADER][SELL SENT] call_id={call.id} {call.mint[:8]}... reason={reason}")

                except Exception as e:
                    call.live_sell_status = "ERROR"
                    call.live_sell_error = str(e)[:300]
                    _last_sent[call.id] = now
                    db.add(call)
                    db.commit()
                    print(f"[TRADER][SELL ERROR] call_id={call.id} err={e}")

        finally:
            db.close()

        await asyncio.sleep(TRADER_POLL_SEC)


def main() -> None:
    asyncio.run(loop())


if __name__ == "__main__":
    main()
