# backend/app/workers/run_recorder.py
from __future__ import annotations

import os
import time
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed

from sqlalchemy import select
from sqlalchemy.orm import Session

from datetime import datetime, timezone

from app.db.session import SessionLocal
from app.models import Call, PricePoint, StrategyResult
from app.workers import pump_ws

DEX_TOKEN_URL = "https://api.dexscreener.com/latest/dex/tokens/"
SOL_CHAIN_ID = "solana"

# Jupiter price API — free, no rate limit stated
JUP_PRICE_URL = "https://lite-api.jup.ag/price/v2"
USDC_MINT = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"

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

# Circuit breaker: if both HTTP APIs fail this many times in a row for a mint,
# skip HTTP for CIRCUIT_BREAK_SEC seconds (pump_ws cache still works).
CIRCUIT_MAX_FAILS = int(os.getenv("CIRCUIT_MAX_FAILS", "5"))
CIRCUIT_BREAK_SEC = int(os.getenv("CIRCUIT_BREAK_SEC", "30"))

# In-memory state per mint: {mint: {"fails": int, "broken_until": float}}
_circuit: dict[str, dict] = {}


def _fetch_price_dexscreener(mint: str) -> float | None:
    """Fetch token price in USD from Dexscreener."""
    try:
        r = requests.get(f"{DEX_TOKEN_URL}{mint}", timeout=8)
        if r.status_code != 200:
            return None
        pairs = r.json().get("pairs") or []
        # Prefer Solana pair
        for p in pairs:
            if p.get("chainId") == SOL_CHAIN_ID and p.get("priceUsd") is not None:
                return float(p["priceUsd"])
        # Any pair
        for p in pairs:
            if p.get("priceUsd") is not None:
                return float(p["priceUsd"])
        return None
    except Exception:
        return None


def _fetch_price_jupiter(mint: str) -> float | None:
    """Fetch token price in USD from Jupiter Price API v2."""
    try:
        r = requests.get(
            JUP_PRICE_URL,
            params={"ids": mint, "vsToken": USDC_MINT},
            timeout=6,
        )
        if r.status_code != 200:
            return None
        data = r.json().get("data") or {}
        item = data.get(mint)
        if item and item.get("price") is not None:
            return float(item["price"])
        return None
    except Exception:
        return None


def _parallel_http_price(mint: str) -> float | None:
    """
    Fire Dexscreener and Jupiter requests simultaneously.
    Return whichever non-None result arrives first.
    Both are cancelled as soon as one succeeds.
    """
    with ThreadPoolExecutor(max_workers=2) as ex:
        futures = {
            ex.submit(_fetch_price_dexscreener, mint): "dex",
            ex.submit(_fetch_price_jupiter, mint): "jup",
        }
        for fut in as_completed(futures):
            try:
                result = fut.result()
                if result is not None:
                    return result
            except Exception:
                pass
    return None


def _fetch_dex_snapshot(mint: str) -> dict | None:
    """
    Fetch the best Solana pair for this mint from Dexscreener and return
    a flat dict of snapshot fields. Returns None on any error.
    """
    try:
        r = requests.get(f"{DEX_TOKEN_URL}{mint}", timeout=8)
        if r.status_code != 200:
            return None
        pairs = r.json().get("pairs") or []
        # Prefer Solana pair with highest liquidity
        sol_pairs = [p for p in pairs if p.get("chainId") == SOL_CHAIN_ID]
        target = None
        if sol_pairs:
            target = max(sol_pairs, key=lambda p: float(p.get("liquidity", {}).get("usd", 0) or 0))
        elif pairs:
            target = pairs[0]
        if not target:
            return None

        vol = target.get("volume") or {}
        pc = target.get("priceChange") or {}
        liq = target.get("liquidity") or {}
        txns = target.get("txns") or {}
        m5 = txns.get("m5") or {}
        h1 = txns.get("h1") or {}

        return {
            "pair_address": target.get("pairAddress"),
            "dex_id": target.get("dexId"),
            "pair_created_at_ms": target.get("pairCreatedAt"),
            "liquidity_usd": float(liq["usd"]) if liq.get("usd") is not None else None,
            "fdv": float(target["fdv"]) if target.get("fdv") is not None else None,
            "market_cap": float(target["marketCap"]) if target.get("marketCap") is not None else None,
            "vol_m5": float(vol["m5"]) if vol.get("m5") is not None else None,
            "vol_h1": float(vol["h1"]) if vol.get("h1") is not None else None,
            "vol_h6": float(vol["h6"]) if vol.get("h6") is not None else None,
            "vol_h24": float(vol["h24"]) if vol.get("h24") is not None else None,
            "pc_m5": float(pc["m5"]) if pc.get("m5") is not None else None,
            "pc_h1": float(pc["h1"]) if pc.get("h1") is not None else None,
            "pc_h6": float(pc["h6"]) if pc.get("h6") is not None else None,
            "pc_h24": float(pc["h24"]) if pc.get("h24") is not None else None,
            "buys_m5": int(m5["buys"]) if m5.get("buys") is not None else None,
            "sells_m5": int(m5["sells"]) if m5.get("sells") is not None else None,
            "buys_h1": int(h1["buys"]) if h1.get("buys") is not None else None,
            "sells_h1": int(h1["sells"]) if h1.get("sells") is not None else None,
        }
    except Exception:
        return None


def fetch_price_usd(mint: str) -> float | None:
    """
    Price resolution order (fastest → slowest):

      1. pump.fun WebSocket cache  — ~200 ms, real-time, pump.fun tokens only
      2. Dexscreener + Jupiter in parallel  — both fired simultaneously
      3. None  — circuit breaker engages after CIRCUIT_MAX_FAILS consecutive misses
    """
    # 1. Real-time pump.fun cache (zero latency, sub-second freshness)
    px = pump_ws.get_cached_price(mint)
    if px is not None:
        return px

    # Circuit breaker check
    state = _circuit.setdefault(mint, {"fails": 0, "broken_until": 0.0})
    if state["broken_until"] > time.time():
        return None

    # 2. Parallel HTTP fetch
    px = _parallel_http_price(mint)
    if px is not None:
        state["fails"] = 0
        return px

    # Both APIs returned nothing — advance circuit breaker
    state["fails"] += 1
    if state["fails"] >= CIRCUIT_MAX_FAILS:
        state["broken_until"] = time.time() + CIRCUIT_BREAK_SEC
        print(
            f"[RECORDER][CIRCUIT OPEN] mint={mint[:8]}... "
            f"all price sources failed {CIRCUIT_MAX_FAILS}x — pausing {CIRCUIT_BREAK_SEC}s",
            flush=True,
        )
        state["fails"] = 0

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
    Also ensures the mint is subscribed to the pump.fun WebSocket feed.
    """
    # Ensure real-time feed is tracking this mint
    pump_ws.subscribe(call.mint)

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
            call.ignore_reason = "no_price_timeout"
        return

    # First successful price becomes entry — also capture full market snapshot
    if call.entry_price_usd is None:
        call.entry_price_usd = float(px)
        snap = _fetch_dex_snapshot(call.mint)
        if snap:
            call.snapshot_at = datetime.now(timezone.utc)
            for field, value in snap.items():
                if value is not None:
                    setattr(call, field, value)
            print(
                f"[RECORDER][SNAPSHOT] call_id={call.id} mint={call.mint[:8]}... "
                f"liq={snap.get('liquidity_usd')} mc={snap.get('market_cap')} "
                f"age_ms={snap.get('pair_created_at_ms')} dex={snap.get('dex_id')}",
                flush=True,
            )

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

    # Start pump.fun real-time WebSocket feed in background
    pump_ws.start_background()

    while True:
        now_ts = time.time()

        # define defaults so sleep() can never crash
        calls: list[Call] = []
        fast_needed = False

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
