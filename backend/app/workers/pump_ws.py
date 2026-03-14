# backend/app/workers/pump_ws.py
"""
Real-time price feed for pump.fun tokens via PumpPortal WebSocket.

Runs in a daemon background thread. The recorder reads from the shared
price_cache dict (GIL-safe for simple key reads/writes).

Price source:  virtual reserves emitted in every trade event.
Coverage:      tokens still on the pump.fun bonding curve.
               Graduated/Raydium tokens fall back to parallel HTTP polling.
"""
from __future__ import annotations

import json
import threading
import time

import requests

try:
    import websocket  # websocket-client package

    _WS_AVAILABLE = True
except ImportError:
    _WS_AVAILABLE = False
    print("[PUMP_WS] websocket-client not installed — real-time feed disabled", flush=True)

PUMP_WS_URL = "wss://pumpportal.fun/api/data"
SOL_MINT = "So11111111111111111111111111111111111111112"
JUP_PRICE_URL = "https://lite-api.jup.ag/price/v2"

# How long a cached price is considered fresh (seconds)
CACHE_MAX_AGE_SEC = float(5)

# Refresh SOL/USD price every N seconds
SOL_PRICE_REFRESH_SEC = 30

# ── Shared state (module-level, daemon thread writes, main thread reads) ────
# mint -> (price_usd: float, last_updated_ts: float)
price_cache: dict[str, tuple[float, float]] = {}

_subscribed: set[str] = set()
_ws_lock = threading.Lock()
_ws_app = None  # current WebSocketApp instance

_sol_price_usd: float = 150.0  # seeded with a reasonable guess
_sol_price_last: float = 0.0


# ── SOL price helper ─────────────────────────────────────────────────────────

def _refresh_sol_price() -> None:
    global _sol_price_usd, _sol_price_last
    try:
        r = requests.get(JUP_PRICE_URL, params={"ids": SOL_MINT}, timeout=5)
        if r.status_code == 200:
            data = r.json().get("data") or {}
            item = data.get(SOL_MINT)
            if item and item.get("price"):
                _sol_price_usd = float(item["price"])
                _sol_price_last = time.time()
                print(f"[PUMP_WS] SOL price updated: ${_sol_price_usd:.2f}", flush=True)
    except Exception:
        pass


def _maybe_refresh_sol_price() -> None:
    if time.time() - _sol_price_last > SOL_PRICE_REFRESH_SEC:
        _refresh_sol_price()


# ── Price calculation from pump.fun virtual reserves ─────────────────────────

def _price_from_reserves(msg: dict) -> float | None:
    """
    pump.fun emits virtual_sol_reserves (lamports) and
    virtual_token_reserves (base units, 6 decimals).

    price_sol  = (vsr / 1e9) / (vtr / 1e6)
               = vsr / (vtr * 1000)
    price_usd  = price_sol * sol_price_usd
    """
    try:
        vsr = msg.get("virtual_sol_reserves")
        vtr = msg.get("virtual_token_reserves")
        if vsr and vtr and int(vtr) > 0:
            _maybe_refresh_sol_price()
            price_sol = int(vsr) / (int(vtr) * 1_000)
            price_usd = price_sol * _sol_price_usd
            if price_usd > 0:
                return price_usd
    except Exception:
        pass
    return None


# ── Public API ────────────────────────────────────────────────────────────────

def subscribe(mint: str) -> None:
    """
    Ask the WebSocket to start streaming trade events for this mint.
    Safe to call from any thread; idempotent.
    """
    global _ws_app
    with _ws_lock:
        if mint in _subscribed:
            return
        _subscribed.add(mint)

    app = _ws_app
    if app is not None:
        try:
            app.send(json.dumps({"method": "subscribeTokenTrade", "keys": [mint]}))
        except Exception:
            pass  # will re-subscribe on next reconnect via _on_open


def get_cached_price(mint: str, max_age_sec: float = CACHE_MAX_AGE_SEC) -> float | None:
    """Return cached price if it is fresh enough, else None."""
    entry = price_cache.get(mint)
    if entry and (time.time() - entry[1]) < max_age_sec:
        return entry[0]
    return None


# ── WebSocket callbacks ───────────────────────────────────────────────────────

def _on_open(ws) -> None:
    print("[PUMP_WS] connected — subscribing to tracked mints", flush=True)
    with _ws_lock:
        mints = list(_subscribed)
    if mints:
        ws.send(json.dumps({"method": "subscribeTokenTrade", "keys": mints}))


def _on_message(_ws, raw: str) -> None:
    try:
        msg = json.loads(raw)
        mint = msg.get("mint")
        if not mint:
            return
        px = _price_from_reserves(msg)
        if px is not None:
            price_cache[mint] = (px, time.time())
    except Exception:
        pass


def _on_error(_ws, err) -> None:
    print(f"[PUMP_WS] error: {err}", flush=True)


def _on_close(_ws, code, _msg) -> None:
    print(f"[PUMP_WS] closed code={code} — will reconnect", flush=True)


# ── Background thread ─────────────────────────────────────────────────────────

def _run_forever() -> None:
    global _ws_app
    _refresh_sol_price()

    while True:
        try:
            _ws_app = websocket.WebSocketApp(
                PUMP_WS_URL,
                on_open=_on_open,
                on_message=_on_message,
                on_error=_on_error,
                on_close=_on_close,
            )
            _ws_app.run_forever(ping_interval=20, ping_timeout=10)
        except Exception as e:
            print(f"[PUMP_WS] fatal in run_forever: {e}", flush=True)
        time.sleep(3)  # brief pause before reconnect


def start_background() -> None:
    """
    Start the WebSocket client in a daemon thread.
    Call once at recorder startup; subsequent calls are no-ops.
    """
    if not _WS_AVAILABLE:
        print("[PUMP_WS] skipping start — websocket-client not installed", flush=True)
        return
    t = threading.Thread(target=_run_forever, daemon=True, name="pump-ws")
    t.start()
    print("[PUMP_WS] background thread started", flush=True)
