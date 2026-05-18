# backend/app/workers/run_backfill.py
"""
Backfill missed signals during bot downtime.

Detects the downtime window, replays missed Telegram messages, fetches
historical price data, simulates trades with configured TP/SL, and stores
results in the backfill_simulations table.

Usage:
    # Auto-detect downtime window from DB
    python -m app.workers.run_backfill

    # Explicit time window
    python -m app.workers.run_backfill --since "2026-03-25 00:00"
    python -m app.workers.run_backfill --since "2026-03-25 00:00" --until "2026-03-25 12:00"

    # Preview only — no DB writes
    python -m app.workers.run_backfill --dry-run

    # Override TP/SL
    python -m app.workers.run_backfill --tp 50 --sl 25
"""
from __future__ import annotations

import os
import re
import sys
import time
import asyncio
import argparse
import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import NamedTuple

import requests
from sqlalchemy import select, func
from sqlalchemy.exc import IntegrityError

from app.db.session import SessionLocal
from app.models import Channel, BackfillSimulation

# ── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="[BACKFILL] %(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("backfill")

# ── Config ───────────────────────────────────────────────────────────────────
TELEGRAM_API_ID   = int(os.environ["TELEGRAM_API_ID"])
TELEGRAM_API_HASH = os.environ["TELEGRAM_API_HASH"]

SESSION_DIR = Path(os.environ.get("TELEGRAM_SESSION_DIR", "/app/sessions"))
# Backfill uses its own session so it never conflicts with the live listener.
# Falls back to the listener session if the backfill session doesn't exist yet.
_BACKFILL_SESSION = os.getenv("TELEGRAM_SESSION_BACKFILL", "tg_lab_session_listener")
SESSION_PATH = str(SESSION_DIR / f"{_BACKFILL_SESSION}.session")

RECORD_DURATION_SEC = int(os.getenv("RECORD_DURATION_SEC", "1500"))

# Dexscreener / GeckoTerminal endpoints
_DEX_TOKEN_URL   = "https://api.dexscreener.com/latest/dex/tokens/"
_GECKO_POOLS_URL = "https://api.geckoterminal.com/api/v2/networks/solana/tokens/{mint}/pools"
_GECKO_OHLCV_URL = (
    "https://api.geckoterminal.com/api/v2/networks/solana/pools/{pool}/ohlcv/minute"
    "?aggregate=1&before_timestamp={before}&limit=1000&token=base"
)

# Min price to consider valid — avoids pre-liquidity candles at near-zero prices
MIN_VALID_PRICE = 1e-10

# Solana CA regex (same as listener)
BASE58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
_CA_RE = re.compile(rf"(?<![{BASE58}])([{BASE58}]{{32,44}})(?:pump)?(?![{BASE58}])")


# ── Data types ────────────────────────────────────────────────────────────────
class SimResult(NamedTuple):
    result: str          # TP | SL | TIME | NO_DATA | NO_ENTRY
    entry_price: float | None
    entry_delay_sec: int | None
    exit_price: float | None
    exit_t_sec: int | None
    pnl_pct: float | None
    max_profit_pct: float | None
    max_drawdown_pct: float | None


# ── 1. Downtime window detection ──────────────────────────────────────────────

def get_downtime_window(
    since_override: datetime | None = None,
    until_override: datetime | None = None,
) -> tuple[datetime, datetime]:
    """
    Returns (since, until) UTC datetimes representing the downtime window.

    Priority:
      1. CLI --since / --until overrides
      2. State file  /app/data/backfill_last_seen.json
      3. MAX(calls.started_at) across all channels in DB minus 5-minute safety buffer
      4. last 1 hour as absolute fallback
    """
    until = until_override or datetime.now(timezone.utc)

    if since_override:
        return since_override, until

    # Try state file
    state_file = Path(os.getenv("BACKFILL_STATE_FILE", "/app/data/backfill_last_seen.txt"))
    if state_file.exists():
        try:
            ts_str = state_file.read_text().strip()
            since = datetime.fromisoformat(ts_str)
            if since.tzinfo is None:
                since = since.replace(tzinfo=timezone.utc)
            log.info(f"Downtime window from state file: {since.isoformat()} → {until.isoformat()}")
            return since, until
        except Exception as e:
            log.warning(f"Could not read state file {state_file}: {e}")

    # Try MAX(calls.started_at) from DB
    db = SessionLocal()
    try:
        from app.models import Call
        row = db.execute(select(func.max(Call.started_at))).scalar_one_or_none()
        if row:
            last_call_ts = row if row.tzinfo else row.replace(tzinfo=timezone.utc)
            # Add 5-minute buffer to avoid re-processing the last few calls
            since = last_call_ts - timedelta(minutes=5)
            log.info(f"Downtime window from DB max(started_at): {since.isoformat()} → {until.isoformat()}")
            return since, until
    except Exception as e:
        log.warning(f"Could not query DB for downtime window: {e}")
    finally:
        db.close()

    # Absolute fallback: last hour
    since = until - timedelta(hours=1)
    log.info(f"Downtime window fallback (last 1h): {since.isoformat()} → {until.isoformat()}")
    return since, until


def save_last_seen(until: datetime) -> None:
    """Write the until timestamp to the state file so the next run knows where to start."""
    state_file = Path(os.getenv("BACKFILL_STATE_FILE", "/app/data/backfill_last_seen.txt"))
    try:
        state_file.parent.mkdir(parents=True, exist_ok=True)
        state_file.write_text(until.isoformat())
    except Exception as e:
        log.warning(f"Could not save state file: {e}")


# ── 2. Fetch missed Telegram messages ─────────────────────────────────────────

def _extract_ca(text: str) -> str | None:
    if not text:
        return None
    m = _CA_RE.search(text)
    return m.group(1) if m else None


def _extract_ca_from_message(msg) -> str | None:
    """Extract CA from message body and entity URLs (mirrors listener logic)."""
    body = (msg.message or "").strip()
    mint = _extract_ca(body)
    if mint:
        return mint
    for entity in (msg.entities or []):
        url = getattr(entity, "url", None)
        if url:
            mint = _extract_ca(url)
            if mint:
                return mint
    return None


async def fetch_missed_messages(
    client,
    channel: Channel,
    since: datetime,
    until: datetime,
) -> list[tuple[str, datetime, str]]:
    """
    Returns list of (mint, detected_at, raw_message) for all CA-containing
    messages in the channel between since and until.
    """
    from telethon.errors import UsernameNotOccupiedError, UsernameInvalidError

    username = (channel.telegram_username or "").lstrip("@")
    if not username:
        log.warning(f"Channel id={channel.id} has no telegram_username — skipping")
        return []

    try:
        entity = await client.get_input_entity(username)
    except (UsernameNotOccupiedError, UsernameInvalidError) as e:
        log.warning(f"Could not resolve @{username}: {e}")
        return []
    except Exception as e:
        log.warning(f"Error resolving @{username}: {e}")
        return []

    results: list[tuple[str, datetime, str]] = []
    seen_mints: set[str] = set()

    log.info(f"  Fetching @{username} messages {since.isoformat()} → {until.isoformat()}")

    # iter_messages with reverse=True + offset_date=since gives messages from since onward
    async for msg in client.iter_messages(entity, reverse=True, offset_date=since, limit=None):
        msg_date = msg.date
        if msg_date.tzinfo is None:
            msg_date = msg_date.replace(tzinfo=timezone.utc)

        if msg_date > until:
            break
        if msg_date < since:
            continue

        mint = _extract_ca_from_message(msg)
        if not mint:
            continue

        # Deduplicate within this fetch (same token can appear in multiple messages)
        if mint in seen_mints:
            log.debug(f"  Dedup mint={mint[:8]}... in @{username}")
            continue
        seen_mints.add(mint)

        raw = (msg.message or "")[:2000]
        results.append((mint, msg_date, raw))
        log.info(f"  Found mint={mint[:8]}... at {msg_date.isoformat()} in @{username}")

    log.info(f"  @{username}: {len(results)} unique token(s) found in window")
    return results


# ── 3. Historical price data ──────────────────────────────────────────────────

def _get_pool_address(mint: str) -> str | None:
    """
    Get the best liquidity pool address for a mint.
    Tries Dexscreener first, then GeckoTerminal.
    """
    # Dexscreener
    try:
        r = requests.get(f"{_DEX_TOKEN_URL}{mint}", timeout=10)
        if r.status_code == 200:
            pairs = r.json().get("pairs") or []
            # Sort by liquidity, prefer Solana
            sol_pairs = [p for p in pairs if p.get("chainId") == "solana"]
            best = sorted(sol_pairs, key=lambda p: float(p.get("liquidity", {}).get("usd") or 0), reverse=True)
            if best:
                return best[0].get("pairAddress")
    except Exception as e:
        log.debug(f"Dexscreener pool lookup failed for {mint[:8]}...: {e}")

    # GeckoTerminal fallback
    try:
        r = requests.get(_GECKO_POOLS_URL.format(mint=mint), timeout=10,
                         headers={"Accept": "application/json"})
        if r.status_code == 200:
            data = r.json().get("data") or []
            if data:
                return data[0]["attributes"]["address"]
    except Exception as e:
        log.debug(f"GeckoTerminal pool lookup failed for {mint[:8]}...: {e}")

    return None


def fetch_historical_prices(
    mint: str,
    from_ts: datetime,
    to_ts: datetime,
    pool_address: str | None = None,
) -> list[tuple[float, float]]:
    """
    Fetch 1-minute OHLCV candles for mint between from_ts and to_ts.
    Returns list of (unix_timestamp, close_price_usd), sorted ascending.

    Uses GeckoTerminal OHLCV (free, no key required).
    Falls back to Dexscreener candles if GeckoTerminal fails.
    """
    if pool_address is None:
        pool_address = _get_pool_address(mint)
    if not pool_address:
        log.warning(f"No pool address found for {mint[:8]}...")
        return []

    candles = _fetch_gecko_ohlcv(pool_address, from_ts, to_ts)
    if candles:
        return candles

    candles = _fetch_dexscreener_candles(pool_address, from_ts, to_ts)
    return candles


def _fetch_gecko_ohlcv(
    pool_address: str,
    from_ts: datetime,
    to_ts: datetime,
) -> list[tuple[float, float]]:
    """Fetch OHLCV from GeckoTerminal. Returns (timestamp, close_price) pairs."""
    before_unix = int(to_ts.timestamp())
    url = _GECKO_OHLCV_URL.format(pool=pool_address, before=before_unix)

    try:
        r = requests.get(url, timeout=15, headers={"Accept": "application/json"})
        if r.status_code != 200:
            log.debug(f"GeckoTerminal OHLCV {r.status_code} for pool {pool_address[:8]}...")
            return []

        data = r.json()
        ohlcv_list = (data.get("data") or {}).get("attributes", {}).get("ohlcv_list") or []

        from_unix = from_ts.timestamp()
        results = []
        for candle in ohlcv_list:
            # Format: [timestamp_ms, open, high, low, close, volume]
            if len(candle) < 5:
                continue
            ts_ms, _, _, _, close = candle[0], candle[1], candle[2], candle[3], candle[4]
            ts = ts_ms / 1000.0 if ts_ms > 1e10 else float(ts_ms)
            price = float(close)
            if ts < from_unix or price < MIN_VALID_PRICE:
                continue
            results.append((ts, price))

        results.sort(key=lambda x: x[0])
        log.debug(f"GeckoTerminal: {len(results)} candles for pool {pool_address[:8]}...")
        return results

    except Exception as e:
        log.debug(f"GeckoTerminal OHLCV error: {e}")
        return []


def _fetch_dexscreener_candles(
    pair_address: str,
    from_ts: datetime,
    to_ts: datetime,
) -> list[tuple[float, float]]:
    """Fetch candles from Dexscreener. Returns (timestamp, close_price) pairs."""
    url = f"https://api.dexscreener.com/latest/dex/candles/solana/{pair_address}"
    params = {
        "from": int(from_ts.timestamp() * 1000),
        "to":   int(to_ts.timestamp() * 1000),
        "res":  "1",
    }
    try:
        r = requests.get(url, params=params, timeout=15)
        if r.status_code != 200:
            log.debug(f"Dexscreener candles {r.status_code} for {pair_address[:8]}...")
            return []

        candles = r.json().get("candles") or []
        from_unix = from_ts.timestamp()
        results = []
        for c in candles:
            ts = float(c.get("t", 0)) / 1000.0  # Dexscreener returns ms
            price = float(c.get("c") or c.get("close") or 0)
            if ts < from_unix or price < MIN_VALID_PRICE:
                continue
            results.append((ts, price))

        results.sort(key=lambda x: x[0])
        log.debug(f"Dexscreener: {len(results)} candles for {pair_address[:8]}...")
        return results

    except Exception as e:
        log.debug(f"Dexscreener candles error: {e}")
        return []


# ── 4. Trade simulation ───────────────────────────────────────────────────────

def simulate_trade(
    candles: list[tuple[float, float]],
    detection_ts: datetime,
    tp_pct: float,
    sl_pct: float,
    duration_sec: int = RECORD_DURATION_SEC,
) -> SimResult:
    """
    Simulate a trade from detection_ts using historical 1-minute candles.

    Entry price: first candle with a VALID price strictly AFTER detection_ts.
    This avoids pre-liquidity prices (e.g. bonding curve near-zero values).

    Returns SimResult with outcome (TP/SL/TIME/NO_DATA/NO_ENTRY).
    """
    if not candles:
        return SimResult("NO_DATA", None, None, None, None, None, None, None)

    detection_unix = detection_ts.timestamp()
    tp_mult = 1.0 + tp_pct / 100.0
    sl_mult = 1.0 - sl_pct / 100.0
    end_unix = detection_unix + duration_sec

    # Find entry: first candle AFTER detection time with a valid price
    entry_price: float | None = None
    entry_unix: float | None = None

    for ts, price in candles:
        if ts <= detection_unix:
            continue  # skip candles at or before detection
        if price < MIN_VALID_PRICE:
            continue  # skip pre-liquidity zero prices
        entry_price = price
        entry_unix = ts
        break

    if entry_price is None:
        return SimResult("NO_ENTRY", None, None, None, None, None, None, None)

    entry_delay_sec = int(entry_unix - detection_unix)
    tp_price = entry_price * tp_mult
    sl_price = entry_price * sl_mult

    max_price = entry_price
    min_price = entry_price

    # Walk forward through candles after entry
    for ts, price in candles:
        if ts <= entry_unix:
            continue
        if ts > end_unix:
            break

        max_price = max(max_price, price)
        min_price = min(min_price, price)

        if price >= tp_price:
            pnl = (price / entry_price - 1.0) * 100.0
            max_profit = (max_price / entry_price - 1.0) * 100.0
            max_dd = (min_price / entry_price - 1.0) * 100.0
            return SimResult(
                "TP",
                entry_price,
                entry_delay_sec,
                price,
                int(ts - detection_unix),
                round(pnl, 2),
                round(max_profit, 2),
                round(max_dd, 2),
            )

        if price <= sl_price:
            pnl = (price / entry_price - 1.0) * 100.0
            max_profit = (max_price / entry_price - 1.0) * 100.0
            max_dd = (min_price / entry_price - 1.0) * 100.0
            return SimResult(
                "SL",
                entry_price,
                entry_delay_sec,
                price,
                int(ts - detection_unix),
                round(pnl, 2),
                round(max_profit, 2),
                round(max_dd, 2),
            )

    # TIME: duration ended without hitting TP or SL
    last_candle = next(
        (p for ts, p in reversed(candles) if ts <= end_unix and ts > entry_unix),
        entry_price,
    )
    pnl = (last_candle / entry_price - 1.0) * 100.0
    max_profit = (max_price / entry_price - 1.0) * 100.0
    max_dd = (min_price / entry_price - 1.0) * 100.0
    return SimResult(
        "TIME",
        entry_price,
        entry_delay_sec,
        last_candle,
        duration_sec,
        round(pnl, 2),
        round(max_profit, 2),
        round(max_dd, 2),
    )


# ── 5. Save results ───────────────────────────────────────────────────────────

def save_result(
    db,
    channel: Channel,
    mint: str,
    detected_at: datetime,
    raw_message: str,
    sim: SimResult,
    tp_pct: float,
    sl_pct: float,
    dry_run: bool = False,
) -> bool:
    """
    Insert a BackfillSimulation row. Returns True if inserted, False if duplicate.
    Safe to call multiple times (unique constraint on channel_id + mint + detected_at).
    """
    row = BackfillSimulation(
        channel_id=channel.id,
        channel_username=channel.telegram_username,
        mint=mint,
        detected_at=detected_at,
        entry_price_usd=sim.entry_price,
        entry_delay_sec=sim.entry_delay_sec,
        exit_price_usd=sim.exit_price,
        exit_t_sec=sim.exit_t_sec,
        tp_pct=tp_pct,
        sl_pct=sl_pct,
        result=sim.result,
        pnl_pct=sim.pnl_pct,
        max_profit_pct=sim.max_profit_pct,
        max_drawdown_pct=sim.max_drawdown_pct,
        raw_message=raw_message,
    )

    if dry_run:
        log.info(
            f"  [DRY-RUN] mint={mint[:8]}... result={sim.result} "
            f"entry={sim.entry_price} pnl={sim.pnl_pct}%"
        )
        return True

    try:
        db.add(row)
        db.commit()
        return True
    except IntegrityError:
        db.rollback()
        log.debug(f"  Duplicate skipped: mint={mint[:8]}... detected_at={detected_at.isoformat()}")
        return False
    except Exception as e:
        db.rollback()
        log.error(f"  DB error saving mint={mint[:8]}...: {e}")
        return False


# ── 6. Main orchestrator ──────────────────────────────────────────────────────

async def run_backfill(
    since: datetime,
    until: datetime,
    tp_pct: float,
    sl_pct: float,
    dry_run: bool,
) -> None:
    from telethon import TelegramClient

    log.info(f"Starting backfill | window={since.isoformat()} → {until.isoformat()}")
    log.info(f"Strategy: TP={tp_pct}% SL={sl_pct}% | dry_run={dry_run}")

    db = SessionLocal()
    try:
        channels = db.execute(
            select(Channel).where(Channel.enabled == True)  # noqa: E712
        ).scalars().all()
    finally:
        db.close()

    if not channels:
        log.warning("No enabled channels found in DB. Nothing to backfill.")
        return

    log.info(f"Processing {len(channels)} channel(s): {[c.telegram_username for c in channels]}")

    client = TelegramClient(SESSION_PATH, TELEGRAM_API_ID, TELEGRAM_API_HASH)
    await client.start()

    total_found = 0
    total_saved = 0
    total_skipped = 0

    for channel in channels:
        log.info(f"\nChannel: @{channel.telegram_username} (id={channel.id})")

        messages = await fetch_missed_messages(client, channel, since, until)
        if not messages:
            log.info(f"  No signals found in window for @{channel.telegram_username}")
            continue

        for mint, detected_at, raw_message in messages:
            total_found += 1
            log.info(f"\n  Processing mint={mint[:8]}... detected_at={detected_at.isoformat()}")

            # Fetch historical prices: start 1 minute before detection for context
            fetch_from = detected_at - timedelta(minutes=1)
            fetch_to   = detected_at + timedelta(seconds=RECORD_DURATION_SEC + 300)

            candles = fetch_historical_prices(mint, fetch_from, fetch_to)
            log.info(f"  {len(candles)} price candles fetched")

            # Add small delay to respect rate limits
            time.sleep(0.5)

            sim = simulate_trade(candles, detected_at, tp_pct, sl_pct)
            log.info(
                f"  Simulation result: {sim.result} | "
                f"entry={sim.entry_price} (+{sim.entry_delay_sec}s delay) | "
                f"pnl={sim.pnl_pct}% | max_profit={sim.max_profit_pct}% | max_dd={sim.max_drawdown_pct}%"
            )

            db = SessionLocal()
            try:
                saved = save_result(
                    db, channel, mint, detected_at, raw_message,
                    sim, tp_pct, sl_pct, dry_run=dry_run,
                )
            finally:
                db.close()

            if saved:
                total_saved += 1
            else:
                total_skipped += 1

    await client.disconnect()

    log.info(
        f"\nBackfill complete | "
        f"found={total_found} saved={total_saved} skipped_duplicates={total_skipped}"
    )

    if not dry_run:
        save_last_seen(until)
        log.info(f"State saved — next run will start from {until.isoformat()}")


# ── CLI entry point ───────────────────────────────────────────────────────────

def _parse_dt(s: str) -> datetime:
    """Parse a datetime string to UTC-aware datetime."""
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M"):
        try:
            dt = datetime.strptime(s, fmt)
            return dt.replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    raise argparse.ArgumentTypeError(
        f"Invalid datetime format: {s!r}. Use 'YYYY-MM-DD HH:MM' or 'YYYY-MM-DD HH:MM:SS'"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill missed signals during bot downtime.")
    parser.add_argument("--since", type=_parse_dt, default=None,
                        help="Start of downtime window, e.g. '2026-03-25 00:00'")
    parser.add_argument("--until", type=_parse_dt, default=None,
                        help="End of downtime window (default: now)")
    parser.add_argument("--tp", type=float, default=float(os.getenv("DISPLAY_TP_PCT", "35")),
                        help="Take-profit %% (default from DISPLAY_TP_PCT env or 35)")
    parser.add_argument("--sl", type=float, default=float(os.getenv("DISPLAY_SL_PCT", "20")),
                        help="Stop-loss %% (default from DISPLAY_SL_PCT env or 20)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print results without saving to DB")
    args = parser.parse_args()

    since, until = get_downtime_window(args.since, args.until)

    if (until - since).total_seconds() < 60:
        log.info("Downtime window is less than 1 minute — nothing to backfill.")
        sys.exit(0)

    asyncio.run(run_backfill(since, until, args.tp, args.sl, args.dry_run))


if __name__ == "__main__":
    main()
