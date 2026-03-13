# backend/app/services/geckoterm.py
"""
GeckoTerminal free API — fetch 1-minute OHLCV candles for a Solana token.
No API key required. Rate limit ~30 req/min.
"""
from __future__ import annotations

import time
import requests
from typing import Optional

BASE = "https://api.geckoterminal.com/api/v2"
HEADERS = {"Accept": "application/json;version=20230302"}


def get_top_pool(mint: str, timeout: int = 8) -> Optional[str]:
    """Return the top pool address for a Solana mint, or None."""
    url = f"{BASE}/networks/solana/tokens/{mint}/pools"
    try:
        r = requests.get(url, headers=HEADERS, params={"page": 1}, timeout=timeout)
        if r.status_code != 200:
            return None
        pools = r.json().get("data") or []
        if not pools:
            return None
        return pools[0]["id"].split("_")[-1]  # "solana_<pool_address>"
    except Exception:
        return None


def get_ohlcv_candles(
    pool_address: str,
    before_timestamp: int,
    limit: int = 40,
    timeout: int = 8,
) -> list[tuple[int, float, float, float, float]]:
    """
    Fetch 1-minute OHLCV candles before a given unix timestamp.
    Returns list of (timestamp, open, high, low, close).
    """
    url = f"{BASE}/networks/solana/pools/{pool_address}/ohlcv/minute"
    params = {
        "aggregate": 1,
        "before_timestamp": before_timestamp,
        "limit": limit,
        "currency": "usd",
    }
    try:
        r = requests.get(url, headers=HEADERS, params=params, timeout=timeout)
        if r.status_code != 200:
            return []
        raw = r.json().get("data", {}).get("attributes", {}).get("ohlcv_list") or []
        # Each item: [timestamp_ms, open, high, low, close, volume]
        result = []
        for item in raw:
            if len(item) < 5:
                continue
            ts = int(item[0]) // 1000  # ms → s
            o, h, l, c = float(item[1]), float(item[2]), float(item[3]), float(item[4])
            result.append((ts, o, h, l, c))
        result.sort(key=lambda x: x[0])
        return result
    except Exception:
        return []


def simulate_with_candles(
    candles: list[tuple[int, float, float, float, float]],
    entry_price: float,
    tp_pct: float,
    sl_pct: float,
    start_ts: int,
    end_ts: int,
) -> tuple[str, float]:
    """
    Simulate TP/SL outcome using OHLCV candles.
    Uses candle high to check TP, candle low to check SL.
    Only considers candles within [start_ts, end_ts].
    Returns (outcome, pnl_pct).
    """
    if entry_price <= 0:
        return ("TIME", 0.0)

    tp_target = entry_price * (1.0 + tp_pct / 100.0)
    sl_target = entry_price * (1.0 - sl_pct / 100.0)

    last_close = entry_price

    for ts, o, h, l, c in candles:
        if ts < start_ts or ts > end_ts:
            continue
        last_close = c

        # Within one candle, check if both TP and SL were touched.
        # Use open price to determine which was hit first.
        tp_hit = h >= tp_target
        sl_hit = l <= sl_target

        if tp_hit and sl_hit:
            # Ambiguous candle — use open price proximity to decide
            tp_dist = abs(o - tp_target)
            sl_dist = abs(o - sl_target)
            if tp_dist <= sl_dist:
                return ("TP", float(tp_pct))
            else:
                return ("SL", -float(sl_pct))

        if tp_hit:
            return ("TP", float(tp_pct))

        if sl_hit:
            return ("SL", -float(sl_pct))

    pnl = ((last_close / entry_price) - 1.0) * 100.0
    return ("TIME", float(pnl))
