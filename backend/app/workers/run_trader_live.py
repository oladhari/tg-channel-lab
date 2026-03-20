# backend/app/workers/run_trader_live.py
from __future__ import annotations

import os
import time
import asyncio
import json
from datetime import datetime, timezone
from typing import Any

import requests
import base58
from solders.keypair import Keypair

from sqlalchemy import select, or_, and_
from sqlalchemy.orm import Session
from sqlalchemy.exc import OperationalError

from app.db.session import SessionLocal
from app.models import Call, Channel, StrategyResult

from app.executors.jup_executor import SOL_MINT, jup_swap_exact_in
from app.executors.raydium_executor import raydium_swap_exact_in
from app.executors.jito_executor import jup_swap_jito, confirm_bundle

USE_JITO = os.getenv("USE_JITO", "1").strip() not in ("0", "false", "False")

RPC_URL = os.getenv("SOLANA_RPC_URL", "https://api.mainnet-beta.solana.com").strip()
# Global fallback — used when a channel has no per-channel TP/SL set
LIVE_STRATEGY_KEY = os.getenv("LIVE_STRATEGY_KEY", "tp35_sl20").strip()


def _channel_strategy_key(ch: Channel) -> str:
    """Per-channel TP/SL if set, otherwise global LIVE_STRATEGY_KEY."""
    tp = getattr(ch, "live_tp_pct", None)
    sl = getattr(ch, "live_sl_pct", None)
    if tp is not None and sl is not None:
        return f"tp{int(tp)}_sl{int(sl)}"
    return LIVE_STRATEGY_KEY


TRADER_POLL_SEC = float(os.getenv("TRADER_POLL_SEC", "2"))
SELL_COOLDOWN_SEC = int(os.getenv("LIVE_SELL_COOLDOWN_SEC", "15"))
# Max age of signal to sell — skip sells for calls older than this (safety net)
MAX_SIGNAL_AGE_SEC = int(os.getenv("LIVE_MAX_SIGNAL_AGE_SEC", "300"))  # 5 minutes
# Jito bundle confirmation timeout before falling back to Jupiter
JITO_CONFIRM_TIMEOUT_SEC = float(os.getenv("LIVE_JITO_CONFIRM_SEC", "3.0"))

# aggressive knobs
LIVE_CONFIRM_MS = int(os.getenv("LIVE_CONFIRM_MS", "5000"))
LIVE_FAST_MODE = os.getenv("LIVE_FAST_MODE", "1").strip() not in ("0", "false", "False")

# Sell percent of *token balance* in wallet (0-100). Default 100 = sell all tokens.
LIVE_SELL_PERCENT = float(os.getenv("LIVE_SELL_PERCENT", "100").strip().replace("%", ""))

# Slippage ladder (bps)
SLIPPAGE_STEPS_BPS = [int(x) for x in os.getenv("LIVE_SLIPPAGE_STEPS_BPS", "2500,5000,10000,20000").split(",")]

# Raydium compute endpoint rejects huge bps -> clamp
RAYDIUM_MAX_BPS = int(os.getenv("LIVE_MAX_SLIPPAGE_BPS_RAYDIUM", os.getenv("RAYDIUM_MAX_SLIPPAGE_BPS", "5000")))
SLIPPAGE_STEPS_BPS_RAYDIUM = sorted({min(int(x), RAYDIUM_MAX_BPS) for x in SLIPPAGE_STEPS_BPS if int(x) > 0})

_last_sent: dict[int, float] = {}  # call_id -> ts


def _get_sig_status(sig: str) -> tuple[str | None, object]:
    """Returns (confirmationStatus, err). err is None if TX succeeded."""
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "getSignatureStatuses",
        "params": [[sig], {"searchTransactionHistory": False}],
    }
    r = requests.post(RPC_URL, json=payload, timeout=1.2)
    r.raise_for_status()
    jr = r.json()
    v = (((jr.get("result") or {}).get("value")) or [None])[0]
    if not v:
        return None, None
    return v.get("confirmationStatus") or None, v.get("err")


def _confirm_fast(sig: str, max_ms: int) -> bool:
    """
    Poll until TX is confirmed (not just processed) or timeout.
    Returns False immediately if TX was included but reverted (err != None).
    "processed" is excluded — it can still be dropped before confirmation.
    """
    deadline = time.time() + (max_ms / 1000.0)
    while time.time() < deadline:
        try:
            st, err = _get_sig_status(sig)
            if err is not None:
                # TX was included in a block but execution failed (e.g. slippage exceeded)
                print(f"[TRADER_LIVE][TX_REVERTED] sig={sig} err={err}", flush=True)
                return False
            if st in ("confirmed", "finalized"):
                return True
        except Exception:
            pass
        time.sleep(0.10)
    return False


def _rpc(method: str, params: list[Any]) -> dict[str, Any]:
    if not RPC_URL:
        raise RuntimeError("SOLANA_RPC_URL is missing")
    payload = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params}
    r = requests.post(RPC_URL, json=payload, timeout=20)
    if r.status_code != 200:
        raise RuntimeError(f"RPC {method} HTTP {r.status_code}: {r.text[:250]}")
    jr = r.json()
    if "error" in jr:
        raise RuntimeError(f"RPC {method} error: {jr['error']}")
    return jr.get("result") or {}


def _load_keypair_from_env() -> Keypair:
    """
    Uses the exact same env key as executors: SOLANA_PRIVATE_KEY
    Accepts:
      - JSON array secret key: [1,2,3,...]
      - base58 secret key
    """
    raw = (os.getenv("SOLANA_PRIVATE_KEY") or "").strip()
    if not raw:
        raise RuntimeError("SOLANA_PRIVATE_KEY is missing")

    # JSON array format
    try:
        data = json.loads(raw)
        if isinstance(data, list) and all(isinstance(x, int) for x in data):
            return Keypair.from_bytes(bytes(data))
    except Exception:
        pass

    # base58 secret key
    try:
        secret = base58.b58decode(raw)
        return Keypair.from_bytes(secret)
    except Exception as e:
        raise RuntimeError(f"Invalid SOLANA_PRIVATE_KEY format: {e}")


def _wallet_pubkey() -> str:
    # ✅ No SOLANA_WALLET_PUBKEY env needed.
    kp = _load_keypair_from_env()
    return str(kp.pubkey())


def _get_token_balance_raw(owner_pubkey: str, mint: str) -> int:
    """
    Returns raw token amount (base units, NOT USD).
    This is what we must sell (wallet can't accept "USD sell").
    """
    result = _rpc(
        "getTokenAccountsByOwner",
        [
            owner_pubkey,
            {"mint": mint},
            {"encoding": "jsonParsed"},
        ],
    )
    value = result.get("value") or []
    total = 0
    for acc in value:
        try:
            amt = int(acc["account"]["data"]["parsed"]["info"]["tokenAmount"]["amount"])
            total += amt
        except Exception:
            continue
    return int(total)


def _compute_sell_amount_raw(balance_raw: int) -> int:
    if balance_raw <= 0:
        return 0
    pct = max(0.0, min(100.0, float(LIVE_SELL_PERCENT)))
    if pct >= 100.0:
        return int(balance_raw)
    # floor is fine; avoids exceeding balance due to rounding
    return int(balance_raw * (pct / 100.0))


def pick_ready_rows(db: Session) -> list[tuple[Call, StrategyResult, Channel]]:
    from datetime import timedelta

    c, sr, ch = Call, StrategyResult, Channel

    cutoff = datetime.now(timezone.utc) - timedelta(seconds=MAX_SIGNAL_AGE_SEC)

    # Fetch calls waiting to be sold:
    #   - DONE calls (normal path: full 25-min recording finished)
    #   - RECORDING calls that have a TP/SL StrategyResult (early-exit path: TP/SL
    #     was hit during recording; price collection still continues for simulations)
    stmt = (
        select(c, sr, ch)
        .join(ch, ch.id == c.channel_id)
        .join(sr, sr.call_id == c.id)
        .where(ch.live_enabled == True)
        .where(
            or_(
                c.status == "DONE",
                and_(c.status == "RECORDING", sr.outcome.in_(["TP", "SL"])),
            )
        )
        .where(c.live_sell_enabled == True)
        .where(c.live_sell_status == "NONE")
        .where(c.started_at >= cutoff)  # skip stale signals (e.g. after bot restart)
        .order_by(c.started_at.asc())
        .limit(200)
    )
    all_rows = list(db.execute(stmt).all())

    # Group all strategy results per call, then pick the best matching one:
    #   1. Exact match for the channel's per-channel TP/SL key
    #   2. Fallback to global LIVE_STRATEGY_KEY
    #   3. Fallback to any available strategy result (so call is never silently skipped)
    from collections import defaultdict
    grouped: dict[int, list] = defaultdict(list)
    for call, strat, channel in all_rows:
        grouped[call.id].append((call, strat, channel))

    result = []
    for call_id, rows in grouped.items():
        call, _, channel = rows[0]
        target_key = _channel_strategy_key(channel)

        strats = {strat.strategy_key: (call, strat, channel) for _, strat, _ in rows}

        chosen = strats.get(target_key) or strats.get(LIVE_STRATEGY_KEY) or rows[0]
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
            print(f"[TRADER_LIVE][DB RETRY] err={str(e)[:200]}", flush=True)
            await asyncio.sleep(2)


def _mark(
    db: Session,
    call: Call,
    *,
    status: str,
    reason: str | None = None,
    method: str | None = None,
    tx: str | None = None,
    err: str | None = None,
) -> None:
    call.live_sell_status = status
    call.live_sell_sent_at = datetime.now(timezone.utc)
    call.live_sell_reason = reason
    call.live_sell_error = err[:300] if err else None

    db.add(call)
    db.commit()


def try_jito_sell(mint: str, in_amount_raw: int) -> str:
    """Submit a TOKEN -> SOL swap as a Jito bundle. Returns bundle_id."""
    last_err: Exception | None = None

    for bps in SLIPPAGE_STEPS_BPS:
        try:
            print(
                f"[TRADER_LIVE][JITO TRY] mint={mint[:8]}... bps={bps} in_amount_raw={in_amount_raw}",
                flush=True,
            )
            bundle_id, _quote = jup_swap_jito(
                input_mint=mint,
                output_mint=SOL_MINT,
                in_amount_raw=in_amount_raw,
                slippage_bps=bps,
                wrap_and_unwrap_sol=True,
            )
            return str(bundle_id)
        except Exception as e:
            last_err = e
            print(f"[TRADER_LIVE][JITO FAIL] mint={mint[:8]}... bps={bps} err={str(e)[:500]}", flush=True)
            continue

    raise RuntimeError(f"Jito sell failed: {last_err}")


def try_jupiter_sell(mint: str, in_amount_raw: int) -> str:
    """
    Sell TOKEN -> SOL (NOT USDT).
    in_amount_raw is token base units.
    """
    last_err: Exception | None = None

    for bps in SLIPPAGE_STEPS_BPS:
        try:
            print(
                f"[TRADER_LIVE][JUP TRY] mint={mint[:8]}... bps={bps} in_amount_raw={in_amount_raw} fast={LIVE_FAST_MODE}",
                flush=True,
            )
            sig, _quote = jup_swap_exact_in(
                input_mint=mint,
                output_mint=SOL_MINT,
                in_amount_raw=in_amount_raw,
                slippage_bps=bps,
                wrap_and_unwrap_sol=True,  # output is SOL => unwrap
                fast_mode=LIVE_FAST_MODE,
            )
            return str(sig)
        except Exception as e:
            last_err = e
            print(f"[TRADER_LIVE][JUP FAIL] mint={mint[:8]}... bps={bps} err={str(e)[:500]}", flush=True)
            continue

    raise RuntimeError(f"Jupiter sell failed: {last_err}")


def try_raydium_sell(mint: str, in_amount_raw: int) -> str:
    """
    Sell TOKEN -> SOL (NOT USDT).
    """
    last_err: Exception | None = None

    for bps in SLIPPAGE_STEPS_BPS_RAYDIUM:
        try:
            print(
                f"[TRADER_LIVE][RAY TRY] mint={mint[:8]}... bps={bps} in_amount_raw={in_amount_raw} fast={LIVE_FAST_MODE}",
                flush=True,
            )
            sigs, _resp = raydium_swap_exact_in(
                input_mint=mint,
                output_mint=SOL_MINT,
                in_amount_raw=in_amount_raw,
                slippage_bps=bps,
                wrap_and_unwrap_sol=True,
                fast_mode=LIVE_FAST_MODE,
            )
            return str(sigs[0]) if sigs else "RAYDIUM_NO_SIG"
        except Exception as e:
            last_err = e
            print(f"[TRADER_LIVE][RAY FAIL] mint={mint[:8]}... bps={bps} err={str(e)[:500]}", flush=True)
            continue

    raise RuntimeError(f"Raydium sell failed: {last_err}")


async def loop() -> None:
    print(
        f"[TRADER_LIVE] starting | poll={TRADER_POLL_SEC}s cooldown={SELL_COOLDOWN_SEC}s "
        f"strategy={LIVE_STRATEGY_KEY} sell_percent={LIVE_SELL_PERCENT} rpc={RPC_URL} "
        f"| fast={LIVE_FAST_MODE} confirm_ms={LIVE_CONFIRM_MS}",
        flush=True,
    )
    print(f"[TRADER_LIVE] slippage_jup_bps={SLIPPAGE_STEPS_BPS}", flush=True)
    print(f"[TRADER_LIVE] slippage_raydium_bps={SLIPPAGE_STEPS_BPS_RAYDIUM} (max={RAYDIUM_MAX_BPS})", flush=True)

    owner_pk = _wallet_pubkey()

    while True:
        db = await open_db_retry()
        try:
            rows = pick_ready_rows(db)

            for call, sr, channel in rows:
                now = time.time()
                last = _last_sent.get(call.id, 0.0)
                if now - last < SELL_COOLDOWN_SEC:
                    continue

                reason = (sr.outcome or "").upper()  # TP|SL|TIME
                mint = call.mint
                effective_key = _channel_strategy_key(channel)
                print(f"[TRADER_LIVE][STRATEGY] call_id={call.id} strategy={effective_key}", flush=True)

                try:
                    bal_raw = _get_token_balance_raw(owner_pk, mint)
                    sell_raw = _compute_sell_amount_raw(bal_raw)

                    signal_age_sec = (datetime.now(timezone.utc) - call.started_at).total_seconds()
                    print(
                        "[TRADER_LIVE][PICK] "
                        f"call_id={call.id} mint={mint[:8]}... reason={reason} "
                        f"signal_age={signal_age_sec:.1f}s "
                        f"balance_raw={bal_raw} sell_raw={sell_raw} pct={LIVE_SELL_PERCENT}",
                        flush=True,
                    )

                    if sell_raw <= 0:
                        # No token in our wallet -> fallback to GMGN.
                        _mark(
                            db,
                            call,
                            status="FALLBACK_GMGN",
                            reason=reason,
                            method="NO_BALANCE",
                            err="No token balance in wallet (likely GMGN-managed or different wallet)",
                        )
                        _last_sent[call.id] = now
                        print(f"[TRADER_LIVE][NO BALANCE] call_id={call.id} -> FALLBACK_GMGN", flush=True)
                        continue

                    jito_err: str | None = None
                    jup_err: str | None = None
                    ray_err: str | None = None

                    # 1) Jito bundle (fastest — ~400ms landing)
                    if USE_JITO:
                        try:
                            bundle_id = try_jito_sell(mint, sell_raw)
                            jito_confirm = confirm_bundle(bundle_id, timeout_sec=JITO_CONFIRM_TIMEOUT_SEC)
                            if jito_confirm in ("confirmed", "finalized"):
                                _mark(db, call, status="SENT", reason=reason, method="JITO", tx=bundle_id)
                                _last_sent[call.id] = now
                                print(f"[TRADER_LIVE][JITO OK] call_id={call.id} bundle={bundle_id} status={jito_confirm}", flush=True)
                                continue
                            elif jito_confirm == "failed":
                                jito_err = f"Jito bundle failed on-chain (bundle={bundle_id})"
                            else:
                                jito_err = f"Jito bundle dropped/timeout (bundle={bundle_id})"
                            print(f"[TRADER_LIVE][JITO NO CONFIRM] call_id={call.id} {jito_err} -> fallback Jupiter", flush=True)
                        except Exception as ej:
                            jito_err = str(ej)[:700]
                            print(f"[TRADER_LIVE][JITO TOTAL FAIL] call_id={call.id} err={jito_err} -> fallback Jupiter", flush=True)

                    # 2) Jupiter (fast, direct RPC)
                    try:
                        tx = try_jupiter_sell(mint, sell_raw)
                        ok = _confirm_fast(tx, LIVE_CONFIRM_MS)
                        if ok:
                            _mark(db, call, status="SENT", reason=reason, method="JUPITER", tx=tx)
                            _last_sent[call.id] = now
                            print(f"[TRADER_LIVE][JUP OK] call_id={call.id} tx={tx}", flush=True)
                            continue

                        _mark(
                            db,
                            call,
                            status="FALLBACK_GMGN",
                            reason=reason,
                            method="JUP_TIMEOUT",
                            err=f"JUP sig not seen within {LIVE_CONFIRM_MS}ms (tx={tx})",
                        )
                        _last_sent[call.id] = now
                        print(f"[TRADER_LIVE][JUP TIMEOUT] call_id={call.id} -> FALLBACK_GMGN tx={tx}", flush=True)
                        continue

                    except Exception as e1:
                        jup_err = str(e1)[:700]
                        print(f"[TRADER_LIVE][JUP TOTAL FAIL] call_id={call.id} err={jup_err}", flush=True)

                    # 3) Raydium (fast)
                    try:
                        tx = try_raydium_sell(mint, sell_raw)
                        ok = (tx != "RAYDIUM_NO_SIG") and _confirm_fast(tx, LIVE_CONFIRM_MS)
                        if ok:
                            _mark(db, call, status="SENT", reason=reason, method="RAYDIUM", tx=tx)
                            _last_sent[call.id] = now
                            print(f"[TRADER_LIVE][RAY OK] call_id={call.id} tx={tx}", flush=True)
                            continue

                        _mark(
                            db,
                            call,
                            status="FALLBACK_GMGN",
                            reason=reason,
                            method="RAY_TIMEOUT",
                            err=f"RAY sig not seen within {LIVE_CONFIRM_MS}ms (tx={tx})",
                        )
                        _last_sent[call.id] = now
                        print(f"[TRADER_LIVE][RAY TIMEOUT] call_id={call.id} -> FALLBACK_GMGN tx={tx}", flush=True)
                        continue

                    except Exception as e2:
                        ray_err = str(e2)[:700]

                    combined = f"JITO: {jito_err} | JUPITER: {jup_err} | RAYDIUM: {ray_err}"
                    _mark(db, call, status="FALLBACK_GMGN", reason=reason, method="AUTO_FAIL", err=combined[:900])
                    _last_sent[call.id] = now
                    print(f"[TRADER_LIVE][AUTO FAIL] call_id={call.id} -> FALLBACK_GMGN", flush=True)
                    print(f"[TRADER_LIVE][AUTO FAIL][DETAIL] {combined[:900]}", flush=True)

                except Exception as fatal_one:
                    _last_sent[call.id] = now
                    _mark(
                        db,
                        call,
                        status="FALLBACK_GMGN",
                        reason=reason,
                        method="FATAL_ONE",
                        err=str(fatal_one)[:900],
                    )
                    print(f"[TRADER_LIVE][FATAL_ONE] call_id={call.id} err={fatal_one}", flush=True)

        finally:
            db.close()

        await asyncio.sleep(TRADER_POLL_SEC)


def main() -> None:
    asyncio.run(loop())


if __name__ == "__main__":
    main()
