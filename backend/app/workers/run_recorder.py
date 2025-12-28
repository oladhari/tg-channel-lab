# backend/app/workers/run_recorder.py
from __future__ import annotations

import os
import time
import requests

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.models import Call, PricePoint, StrategyResult

DEX_TOKEN_URL = "https://api.dexscreener.com/latest/dex/tokens/"
SOL_CHAIN_ID = "solana"

# Recording settings
RECORD_DURATION_SEC = int(os.getenv("RECORD_DURATION_SEC", "1500"))

# Adaptive polling: fast for first N seconds of a call, then slower
POLL_FAST_SEC = int(os.getenv("POLL_FAST_SEC", "120"))  # fast window duration (seconds)
FAST_INT = int(os.getenv("POLL_FAST_INTERVAL_SEC", "2"))
SLOW_INT = int(os.getenv("POLL_SLOW_INTERVAL_SEC", "5"))

# If we can't get an entry price after this many seconds, stop tracking
NO_PRICE_TIMEOUT_SEC = int(os.getenv("NO_PRICE_TIMEOUT_SEC", "30"))

# Display strategy (only for UI / quick reading)
TP_PCT = float(os.getenv("DISPLAY_TP_PCT", "35"))
SL_PCT = float(os.getenv("DISPLAY_SL_PCT", "20"))

TP_MULT = 1.0 + TP_PCT / 100.0
SL_MULT = 1.0 - SL_PCT / 100.0


def fetch_price_usd(mint: str) -> float | None:
    """
    Fetch token price in USD from Dexscreener.
    Prefer Solana pairs, fallback to any pair with priceUsd.
    """
    try:
        r = requests.get(f"{DEX_TOKEN_URL}{mint}", timeout=8)
        if r.status_code != 200:
            return None

        j = r.json()
        pairs = j.get("pairs") or []
        if not pairs:
            return None

        # Prefer Solana pair first
        for p in pairs:
            if p.get("chainId") == SOL_CHAIN_ID and p.get("priceUsd") is not None:
                return float(p["priceUsd"])

        # Fallback: any pair
        for p in pairs:
            if p.get("priceUsd") is not None:
                return float(p["priceUsd"])

        return None
    except Exception:
        return None


def compute_display_result(
    points: list[tuple[int, float]],
    entry_price: float,
) -> tuple[str, int, float, float]:
    """
    points: list of (t_sec, price_usd), ascending by t_sec
    return: (outcome TP|SL|TIME, exit_t_sec, exit_price_usd, pnl_pct)
    """
    tp_price = entry_price * TP_MULT
    sl_price = entry_price * SL_MULT

    for t, px in points:
        if px >= tp_price:
            pnl_pct = (px / entry_price - 1.0) * 100.0
            return ("TP", int(t), float(px), float(pnl_pct))
        if px <= sl_price:
            pnl_pct = (px / entry_price - 1.0) * 100.0
            return ("SL", int(t), float(px), float(pnl_pct))

    # TIME exit at last point
    t_last, px_last = points[-1]
    pnl_pct = (px_last / entry_price - 1.0) * 100.0
    return ("TIME", int(t_last), float(px_last), float(pnl_pct))


def record_tick(db: Session, call: Call, now_ts: float) -> None:
    """
    Record one price point for this call at the current second (t_sec).
    Sets entry_price_usd on first successful price fetch.
    """
    started_ts = call.started_at.timestamp()
    t_sec = int(now_ts - started_ts)
    if t_sec < 0:
        t_sec = 0
    if t_sec > call.duration_sec:
        t_sec = call.duration_sec

    # Deduplicate per second
    exists = db.execute(
        select(PricePoint.id).where(
            PricePoint.call_id == call.id,
            PricePoint.t_sec == t_sec,
        )
    ).scalar_one_or_none()
    if exists:
        return

    px = fetch_price_usd(call.mint)

    if px is None:
        # If we couldn't get an entry price for too long, ignore and stop tracking
        if call.entry_price_usd is None and t_sec >= NO_PRICE_TIMEOUT_SEC:
            call.status = "IGNORED_NO_PRICE"
            call.ignore_reason = "dexscreener_no_price_timeout"
        return

    # First successful price becomes entry
    if call.entry_price_usd is None:
        call.entry_price_usd = float(px)

    db.add(
        PricePoint(
            call_id=call.id,
            t_sec=t_sec,
            price_usd=float(px),
        )
    )


def finalize_call(db: Session, call: Call) -> None:
    """
    Compute display strategy result (TP35/SL20 by env) and mark call DONE.
    """
    rows = db.execute(
        select(PricePoint.t_sec, PricePoint.price_usd)
        .where(PricePoint.call_id == call.id)
        .order_by(PricePoint.t_sec.asc())
    ).all()

    if not rows or call.entry_price_usd is None:
        call.status = "IGNORED_NO_PRICE"
        call.ignore_reason = call.ignore_reason or "no_points"
        return

    # Convert SQLAlchemy Row -> tuple[int,float]
    points: list[tuple[int, float]] = [(int(r[0]), float(r[1])) for r in rows]

    outcome, exit_t, exit_px, pnl_pct = compute_display_result(points, float(call.entry_price_usd))

    key = f"tp{int(TP_PCT)}_sl{int(SL_PCT)}"

    existing = db.execute(
        select(StrategyResult).where(
            StrategyResult.call_id == call.id,
            StrategyResult.strategy_key == key,
        )
    ).scalar_one_or_none()

    sr = existing or StrategyResult(call_id=call.id, strategy_key=key)
    sr.tp_pct = float(TP_PCT)
    sr.sl_pct = float(SL_PCT)
    sr.entry_price_usd = float(call.entry_price_usd)
    sr.exit_price_usd = float(exit_px)
    sr.exit_t_sec = int(exit_t)
    sr.outcome = str(outcome)
    sr.pnl_pct = float(round(pnl_pct, 6))

    db.add(sr)
    call.status = "DONE"


def main() -> None:
    print("[RECORDER] started")

    while True:
        now_ts = time.time()

        db = SessionLocal()
        try:
            calls = db.query(Call).filter(Call.status == "RECORDING").all()

            # Decide polling speed based on whether any active call is within fast window
            fast_needed = any((now_ts - c.started_at.timestamp()) < POLL_FAST_SEC for c in calls)

            for call in calls:
                elapsed = int(now_ts - call.started_at.timestamp())

                # Call-level duration check
                if elapsed >= call.duration_sec:
                    finalize_call(db, call)
                    continue

                # Record one tick
                record_tick(db, call, now_ts)

            db.commit()

            # Optional tiny log (comment out if you want quiet)
            if calls:
                mode = "FAST" if fast_needed else "SLOW"
                print(f"[RECORDER] active={len(calls)} mode={mode}")

        except Exception as e:
            db.rollback()
            print(f"[RECORDER] error: {e}")
        finally:
            db.close()

        time.sleep(FAST_INT if (calls and fast_needed) else SLOW_INT)


if __name__ == "__main__":
    main()
