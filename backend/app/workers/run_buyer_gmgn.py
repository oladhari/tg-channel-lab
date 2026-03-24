# backend/app/workers/run_buyer_gmgn.py
from __future__ import annotations

import os
import time
import asyncio
from datetime import datetime, timezone, timedelta
from pathlib import Path

from telethon import TelegramClient
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.db.session import SessionLocal
from app.models import Call

GMGN_TARGET = os.getenv("GMGN_TARGET", "").strip()

# Fallback default (ONLY if call+channel missing)
LIVE_BUY_AMOUNT_SOL = float(os.getenv("LIVE_BUY_AMOUNT_SOL", "0.1"))

BUY_POLL_SEC = float(os.getenv("BUYER_POLL_SEC", "1"))
BUY_COOLDOWN_SEC = int(os.getenv("GMGN_BUY_COOLDOWN_SEC", "15"))
MAX_SIGNAL_AGE_SEC = int(os.getenv("LIVE_MAX_SIGNAL_AGE_SEC", "30"))

TELEGRAM_API_ID = int(os.environ["TELEGRAM_API_ID"])
TELEGRAM_API_HASH = os.environ["TELEGRAM_API_HASH"]

SESSION_DIR = Path(os.environ.get("TELEGRAM_SESSION_DIR", "/app/sessions"))
SESSION_DIR.mkdir(parents=True, exist_ok=True)

BUYER_SESSION_NAME = os.environ.get("TELEGRAM_SESSION_BUYER", "tg_lab_session_buyer").strip()
if not BUYER_SESSION_NAME:
    raise SystemExit("[BUYER_GMGN] TELEGRAM_SESSION_BUYER is empty")

SESSION_PATH = str(SESSION_DIR / f"{BUYER_SESSION_NAME}.session")

# No file lock needed — this client is send-only (receive_updates=False).
# The exclusive lock is only needed for the listener to prevent duplicate event handlers.

client = TelegramClient(SESSION_PATH, TELEGRAM_API_ID, TELEGRAM_API_HASH, receive_updates=False)

_last_sent: dict[int, float] = {}  # call_id -> ts


def _resolve_amount(call: Call) -> tuple[float, str, dict]:
    """
    Source of truth:
      1) call.live_buy_amount_sol (ONLY if explicitly set as per-call override)
      2) call.channel.live_buy_amount_sol (UI default)
      3) env LIVE_BUY_AMOUNT_SOL
    """
    env_default = float(LIVE_BUY_AMOUNT_SOL)

    call_amt = getattr(call, "live_buy_amount_sol", None)

    ch = getattr(call, "channel", None)
    channel_loaded = ch is not None
    chan_amt = getattr(ch, "live_buy_amount_sol", None) if ch is not None else None

    if call_amt is not None:
        return float(call_amt), "CALL", {
            "call_amount": call_amt,
            "channel_amount": chan_amt,
            "env_default": env_default,
            "channel_loaded": channel_loaded,
        }

    if chan_amt is not None:
        return float(chan_amt), "CHANNEL", {
            "call_amount": call_amt,
            "channel_amount": chan_amt,
            "env_default": env_default,
            "channel_loaded": channel_loaded,
        }

    return env_default, "ENV", {
        "call_amount": call_amt,
        "channel_amount": chan_amt,
        "env_default": env_default,
        "channel_loaded": channel_loaded,
    }


async def gmgn_buy(mint: str, amount_sol: float) -> None:
    cmd = f"/buy {mint} {amount_sol}"
    await client.send_message(GMGN_TARGET, cmd)


def pick_ready_calls(db: Session) -> list[Call]:
    c = Call
    cutoff = datetime.now(timezone.utc) - timedelta(seconds=MAX_SIGNAL_AGE_SEC)
    stmt = (
        select(c)
        .options(joinedload(c.channel))  # IMPORTANT: load Channel for UI amount
        .where(c.live_buy_enabled == True)  # noqa: E712
        .where(c.live_buy_status == "FALLBACK_GMGN")
        .where(c.status == "RECORDING")
        .where(c.entry_price_usd.isnot(None))
        .where(c.started_at >= cutoff)  # skip stale signals after restart
        .order_by(c.started_at.asc())
        .limit(50)
    )
    return list(db.execute(stmt).scalars().all())


async def loop() -> None:
    if not GMGN_TARGET:
        raise SystemExit("[BUYER_GMGN] GMGN_TARGET is empty. Set it in .env")

    print(
        f"[BUYER_GMGN] starting | session={SESSION_PATH} | target={GMGN_TARGET} "
        f"| env_default_amount={LIVE_BUY_AMOUNT_SOL} SOL | poll={BUY_POLL_SEC}s | cooldown={BUY_COOLDOWN_SEC}s",
        flush=True,
    )

    await client.connect()
    if not await client.is_user_authorized():
        raise SystemExit(
            f"[BUYER_GMGN] Telegram session not authorized: {SESSION_PATH}. "
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

                amount, src, dbg = _resolve_amount(call)
                print(
                    "[BUYER_GMGN][PICK] "
                    f"call_id={call.id} mint={call.mint[:8]}... "
                    f"resolved_amount={amount} source={src} "
                    f"call_amount={dbg['call_amount']} channel_amount={dbg['channel_amount']} "
                    f"env_default={dbg['env_default']} channel_loaded={dbg['channel_loaded']}",
                    flush=True,
                )

                try:
                    await gmgn_buy(call.mint, amount)

                    call.live_buy_status = "SENT"
                    call.live_buy_sent_at = datetime.now(timezone.utc)
                    call.live_buy_error = None

                    # IMPORTANT:
                    # Do NOT snapshot resolved amount into call.live_buy_amount_sol automatically.
                    # That would "lock" the call to env default 0.1 if it was used once.
                    # call.live_buy_amount_sol should only be set if you explicitly override per-call.

                    _last_sent[call.id] = now
                    db.add(call)
                    db.commit()

                    print(
                        f"[BUYER_GMGN][BUY SENT] call_id={call.id} {call.mint[:8]}... amount={amount} source={src}",
                        flush=True,
                    )

                except Exception as e:
                    call.live_buy_status = "ERROR"
                    call.live_buy_error = str(e)

                    _last_sent[call.id] = now
                    db.add(call)
                    db.commit()

                    print(f"[BUYER_GMGN][BUY ERROR] call_id={call.id} err={e}", flush=True)

        finally:
            db.close()

        await asyncio.sleep(BUY_POLL_SEC)


def main() -> None:
    asyncio.run(loop())


if __name__ == "__main__":
    main()

