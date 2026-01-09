# backend/app/workers/run_buyer_gmgn.py
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
from app.models import Call

GMGN_TARGET = os.getenv("GMGN_TARGET", "").strip()

# default buy amount (global var for now)
LIVE_BUY_AMOUNT_SOL = float(os.getenv("LIVE_BUY_AMOUNT_SOL", "0.1"))

BUY_POLL_SEC = int(os.getenv("BUYER_POLL_SEC", "2"))
BUY_COOLDOWN_SEC = int(os.getenv("GMGN_BUY_COOLDOWN_SEC", "15"))

TELEGRAM_API_ID = int(os.environ["TELEGRAM_API_ID"])
TELEGRAM_API_HASH = os.environ["TELEGRAM_API_HASH"]

# separate sqlite session for buyer

SESSION_DIR = Path(os.environ.get("TELEGRAM_SESSION_DIR", "/app/sessions"))
SESSION_DIR.mkdir(parents=True, exist_ok=True)

BUYER_SESSION_NAME = os.environ.get("TELEGRAM_SESSION_BUYER", "tg_lab_session_buyer").strip()
if not BUYER_SESSION_NAME:
    raise SystemExit("[BUYER] TELEGRAM_SESSION_BUYER is empty")

SESSION_PATH = str(SESSION_DIR / f"{BUYER_SESSION_NAME}.session")

client = TelegramClient(SESSION_PATH, TELEGRAM_API_ID, TELEGRAM_API_HASH)


_last_sent: dict[int, float] = {}  # call_id -> ts


async def gmgn_buy(mint: str, amount_sol: float) -> None:
    # GMGN format: /buy <mint> <amount>
    cmd = f"/buy {mint} {amount_sol}"
    await client.send_message(GMGN_TARGET, cmd)


def pick_ready_calls(db: Session) -> list[Call]:
    c = Call
    stmt = (
        select(c)
        .where(c.live_buy_enabled == True)        # noqa: E712
        .where(c.live_buy_status == "NONE")
        .where(c.status == "RECORDING")          # ✅ only buy active calls
        .where(c.entry_price_usd.isnot(None))    # ✅ wait until we have first price point
        .order_by(c.started_at.asc())
        .limit(50)
    )
    return list(db.execute(stmt).scalars().all())


async def loop() -> None:
    if not GMGN_TARGET:
        raise SystemExit("[BUYER] GMGN_TARGET is empty. Set it in .env")

    print(
        f"[BUYER] starting | session={SESSION_PATH} | target={GMGN_TARGET} "
        f"| amount={LIVE_BUY_AMOUNT_SOL} SOL | poll={BUY_POLL_SEC}s | cooldown={BUY_COOLDOWN_SEC}s"
    )

    await client.connect()
    if not await client.is_user_authorized():
        raise SystemExit(
            f"[BUYER] Telegram session not authorized: {SESSION_PATH}. "
            "Create it once interactively, then restart buyer."
        )

    while True:
        db = SessionLocal()
        try:
            calls = pick_ready_calls(db)

            for call in calls:
                now = time.time()
                last = _last_sent.get(call.id, 0.0)
                if now - last < BUY_COOLDOWN_SEC:
                    continue

                amount = float(call.live_buy_amount_sol or LIVE_BUY_AMOUNT_SOL)

                try:
                    await gmgn_buy(call.mint, amount)

                    call.live_buy_status = "SENT"
                    call.live_buy_sent_at = datetime.now(timezone.utc)
                    call.live_buy_error = None
                    call.live_buy_amount_sol = amount

                    _last_sent[call.id] = now
                    db.add(call)
                    db.commit()

                    print(f"[BUYER][BUY SENT] call_id={call.id} {call.mint[:8]}... amount={amount}")

                except Exception as e:
                    call.live_buy_status = "ERROR"
                    call.live_buy_error = str(e)[:300]
                    call.live_buy_amount_sol = amount

                    _last_sent[call.id] = now
                    db.add(call)
                    db.commit()

                    print(f"[BUYER][BUY ERROR] call_id={call.id} err={e}")

        finally:
            db.close()

        await asyncio.sleep(BUY_POLL_SEC)


def main() -> None:
    asyncio.run(loop())


if __name__ == "__main__":
    main()
