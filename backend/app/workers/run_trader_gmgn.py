# backend/app/workers/run_trader_gmgn.py
from __future__ import annotations

import os
import time
import asyncio
from datetime import datetime, timezone, timedelta
from pathlib import Path

from telethon import TelegramClient
from sqlalchemy import select, or_, and_
from sqlalchemy.orm import Session
from sqlalchemy.exc import OperationalError

from app.db.session import SessionLocal
from app.models import Call, Channel, StrategyResult


GMGN_TARGET = os.getenv("GMGN_TARGET", "").strip()
GMGN_SELL_PERCENT = os.getenv("GMGN_SELL_PERCENT", "100%").strip()
LIVE_STRATEGY_KEY = os.getenv("LIVE_STRATEGY_KEY", "tp35_sl20").strip()
TRADER_POLL_SEC = int(os.getenv("TRADER_POLL_SEC", "2"))
MAX_SIGNAL_AGE_SEC = int(os.getenv("LIVE_MAX_SIGNAL_AGE_SEC", "30"))

SELL_COOLDOWN_SEC = int(os.getenv("GMGN_SELL_COOLDOWN_SEC", os.getenv("GMGN_COOLDOWN_SEC", "45")))

TELEGRAM_API_ID = int(os.environ["TELEGRAM_API_ID"])
TELEGRAM_API_HASH = os.environ["TELEGRAM_API_HASH"]

SESSION_DIR = Path(os.environ.get("TELEGRAM_SESSION_DIR", "/app/sessions"))
SESSION_DIR.mkdir(parents=True, exist_ok=True)

TRADER_SESSION_NAME = os.environ.get("TELEGRAM_SESSION_TRADER", "tg_lab_session_trader").strip()
if not TRADER_SESSION_NAME:
    raise SystemExit("[TRADER_GMGN] TELEGRAM_SESSION_TRADER is empty")

SESSION_PATH = str(SESSION_DIR / f"{TRADER_SESSION_NAME}.session")

# No file lock needed — this client is send-only (receive_updates=False).
# The exclusive lock is only needed for the listener to prevent duplicate event handlers.

client = TelegramClient(SESSION_PATH, TELEGRAM_API_ID, TELEGRAM_API_HASH, receive_updates=False)

_last_sent: dict[int, float] = {}  # call_id -> ts


def _channel_strategy_key(ch: Channel) -> str:
    """Per-channel TP/SL if set, otherwise global LIVE_STRATEGY_KEY."""
    tp = getattr(ch, "live_tp_pct", None)
    sl = getattr(ch, "live_sl_pct", None)
    if tp is not None and sl is not None:
        return f"tp{int(tp)}_sl{int(sl)}"
    return LIVE_STRATEGY_KEY


async def gmgn_sell(mint: str) -> None:
    cmd = f"/sell {mint} {GMGN_SELL_PERCENT}"
    await client.send_message(GMGN_TARGET, cmd)


def pick_ready_calls(db: Session) -> list[tuple[Call, StrategyResult]]:
    from collections import defaultdict
    c, sr, ch = Call, StrategyResult, Channel
    cutoff = datetime.now(timezone.utc) - timedelta(seconds=MAX_SIGNAL_AGE_SEC)
    stmt = (
        select(c, sr, ch)
        .join(ch, ch.id == c.channel_id)
        .join(sr, sr.call_id == c.id)
        .where(
            or_(
                c.status == "DONE",
                and_(c.status == "RECORDING", sr.outcome.in_(["TP", "SL"])),
            )
        )
        .where(c.live_sell_enabled == True)  # noqa: E712
        .where(c.live_sell_status == "FALLBACK_GMGN")  # ONLY fallback
        .where(
            or_(
                c.live_buy_status == "SENT",   # already holding — always sell
                c.started_at >= cutoff,         # fresh signal — apply normal age gate
            )
        )
        .order_by(c.started_at.asc())
        .limit(200)
    )
    all_rows = list(db.execute(stmt).all())

    # Pick best matching StrategyResult per call (mirrors trader_live logic)
    grouped: dict[int, list] = defaultdict(list)
    for call, strat, channel in all_rows:
        grouped[call.id].append((call, strat, channel))

    result = []
    for call_id, rows in grouped.items():
        call, _, channel = rows[0]
        target_key = _channel_strategy_key(channel)
        strats = {strat.strategy_key: (call, strat) for _, strat, _ in rows}
        chosen = strats.get(target_key) or strats.get(LIVE_STRATEGY_KEY) or (rows[0][0], rows[0][1])
        result.append(chosen)

    result.sort(key=lambda r: r[0].started_at)
    return result[:50]


async def open_db_retry(max_wait_sec: int = 60) -> Session:
    start = time.time()
    while True:
        try:
            db = SessionLocal()
            db.execute(select(1))
            return db
        except OperationalError as e:
            if time.time() - start > max_wait_sec:
                raise
            print(f"[TRADER_GMGN][DB RETRY] err={str(e)[:200]}", flush=True)
            await asyncio.sleep(2)


async def loop() -> None:
    if not GMGN_TARGET:
        raise SystemExit("[TRADER_GMGN] GMGN_TARGET is empty. Set it in .env")

    print(
        f"[TRADER_GMGN] starting | session={SESSION_PATH} | target={GMGN_TARGET} "
        f"| strategy={LIVE_STRATEGY_KEY} | poll={TRADER_POLL_SEC}s | cooldown={SELL_COOLDOWN_SEC}s "
        f"| sell_percent={GMGN_SELL_PERCENT}",
        flush=True,
    )

    await client.connect()
    if not await client.is_user_authorized():
        raise SystemExit(
            f"[TRADER_GMGN] Telegram session not authorized: {SESSION_PATH}. "
            "Create it once interactively, then restart trader."
        )

    while True:
        db = await open_db_retry()
        try:
            rows = pick_ready_calls(db)

            for call, sr in rows:
                now = time.time()
                last = _last_sent.get(call.id, 0.0)
                if now - last < SELL_COOLDOWN_SEC:
                    continue

                reason = (sr.outcome or "").upper()  # TP|SL|TIME
                print(f"[TRADER_GMGN][PICK] call_id={call.id} {call.mint[:8]}... reason={reason}", flush=True)

                try:
                    await gmgn_sell(call.mint)

                    call.live_sell_status = "SENT"
                    call.live_sell_reason = reason
                    call.live_sell_sent_at = datetime.now(timezone.utc)
                    call.live_sell_error = None

                    _last_sent[call.id] = now
                    db.add(call)
                    db.commit()

                    print(f"[TRADER_GMGN][SELL SENT] call_id={call.id} {call.mint[:8]}... reason={reason}", flush=True)

                except Exception as e:
                    call.live_sell_status = "ERROR"
                    call.live_sell_error = str(e)

                    _last_sent[call.id] = now
                    db.add(call)
                    db.commit()

                    print(f"[TRADER_GMGN][SELL ERROR] call_id={call.id} err={e}", flush=True)

        finally:
            db.close()

        await asyncio.sleep(TRADER_POLL_SEC)


def main() -> None:
    asyncio.run(loop())


if __name__ == "__main__":
    main()
