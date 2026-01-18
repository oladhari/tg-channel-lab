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

from sqlalchemy import select
from sqlalchemy.orm import Session
from sqlalchemy.exc import OperationalError

from app.db.session import SessionLocal
from app.models import Call, Channel, StrategyResult


from app.executors.jup_executor import SOL_MINT, jup_swap_exact_in
from app.executors.raydium_executor import raydium_swap_exact_in

RPC_URL = os.getenv("SOLANA_RPC_URL", "https://api.mainnet-beta.solana.com").strip()
LIVE_STRATEGY_KEY = os.getenv("LIVE_STRATEGY_KEY", "tp35_sl20").strip()

TRADER_POLL_SEC = int(os.getenv("TRADER_POLL_SEC", "5"))
SELL_COOLDOWN_SEC = int(os.getenv("LIVE_SELL_COOLDOWN_SEC", "15"))

# Sell percent of *token balance* in wallet (0-100). Default 100 = sell all tokens.
LIVE_SELL_PERCENT = float(os.getenv("LIVE_SELL_PERCENT", "100").strip().replace("%", ""))

# Slippage ladder (bps)
SLIPPAGE_STEPS_BPS = [int(x) for x in os.getenv("LIVE_SLIPPAGE_STEPS_BPS", "2500,5000,10000,20000").split(",")]

# Raydium compute endpoint rejects huge bps -> clamp
RAYDIUM_MAX_BPS = int(os.getenv("LIVE_MAX_SLIPPAGE_BPS_RAYDIUM", os.getenv("RAYDIUM_MAX_SLIPPAGE_BPS", "5000")))
SLIPPAGE_STEPS_BPS_RAYDIUM = sorted({min(int(x), RAYDIUM_MAX_BPS) for x in SLIPPAGE_STEPS_BPS if int(x) > 0})

_last_sent: dict[int, float] = {}  # call_id -> ts


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


def pick_ready_rows(db: Session) -> list[tuple[Call, StrategyResult]]:
    c, sr, ch = Call, StrategyResult, Channel

    stmt = (
        select(c, sr)
        .join(ch, ch.id == c.channel_id)
        .join(sr, sr.call_id == c.id)
        .where(ch.live_enabled == True)          # ✅ ADD THIS
        .where(c.status == "DONE")
        .where(c.live_sell_enabled == True)
        .where(c.live_sell_status == "NONE")
        .where(sr.strategy_key == LIVE_STRATEGY_KEY)
        .order_by(c.started_at.asc())
        .limit(50)
    )
    return list(db.execute(stmt).all())



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

    # optional columns if you add them later
    if hasattr(call, "live_sell_method"):
        call.live_sell_method = method
    if hasattr(call, "live_sell_tx_sig"):
        call.live_sell_tx_sig = tx

    db.add(call)
    db.commit()


def try_jupiter_sell(mint: str, in_amount_raw: int) -> str:
    """
    Sell TOKEN -> SOL (NOT USDT).
    in_amount_raw is token base units.
    """
    last_err: Exception | None = None

    for bps in SLIPPAGE_STEPS_BPS:
        try:
            print(
                f"[TRADER_LIVE][JUP TRY] mint={mint[:8]}... bps={bps} in_amount_raw={in_amount_raw}",
                flush=True,
            )
            sig, _quote = jup_swap_exact_in(
                input_mint=mint,
                output_mint=SOL_MINT,
                in_amount_raw=in_amount_raw,
                slippage_bps=bps,
                wrap_and_unwrap_sol=True,  # output is SOL => unwrap
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
                f"[TRADER_LIVE][RAY TRY] mint={mint[:8]}... bps={bps} in_amount_raw={in_amount_raw}",
                flush=True,
            )
            sigs, _resp = raydium_swap_exact_in(
                input_mint=mint,
                output_mint=SOL_MINT,
                in_amount_raw=in_amount_raw,
                slippage_bps=bps,
                wrap_and_unwrap_sol=True,
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
        f"strategy={LIVE_STRATEGY_KEY} sell_percent={LIVE_SELL_PERCENT} rpc={RPC_URL}",
        flush=True,
    )
    print(f"[TRADER_LIVE] slippage_jup_bps={SLIPPAGE_STEPS_BPS}", flush=True)
    print(f"[TRADER_LIVE] slippage_raydium_bps={SLIPPAGE_STEPS_BPS_RAYDIUM} (max={RAYDIUM_MAX_BPS})", flush=True)

    owner_pk = _wallet_pubkey()

    while True:
        db = await open_db_retry()
        try:
            rows = pick_ready_rows(db)

            for call, sr in rows:
                now = time.time()
                last = _last_sent.get(call.id, 0.0)
                if now - last < SELL_COOLDOWN_SEC:
                    continue

                reason = (sr.outcome or "").upper()  # TP|SL|TIME
                mint = call.mint

                try:
                    bal_raw = _get_token_balance_raw(owner_pk, mint)
                    sell_raw = _compute_sell_amount_raw(bal_raw)

                    print(
                        "[TRADER_LIVE][PICK] "
                        f"call_id={call.id} mint={mint[:8]}... reason={reason} "
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

                    jup_err: str | None = None
                    ray_err: str | None = None

                    try:
                        tx = try_jupiter_sell(mint, sell_raw)
                        _mark(db, call, status="SENT", reason=reason, method="JUPITER", tx=tx)
                        _last_sent[call.id] = now
                        print(f"[TRADER_LIVE][JUP OK] call_id={call.id} tx={tx}", flush=True)
                        continue
                    except Exception as e1:
                        jup_err = str(e1)[:700]
                        print(f"[TRADER_LIVE][JUP TOTAL FAIL] call_id={call.id} err={jup_err}", flush=True)

                    try:
                        tx = try_raydium_sell(mint, sell_raw)
                        _mark(db, call, status="SENT", reason=reason, method="RAYDIUM", tx=tx)
                        _last_sent[call.id] = now
                        print(f"[TRADER_LIVE][RAY OK] call_id={call.id} tx={tx}", flush=True)
                        continue
                    except Exception as e2:
                        ray_err = str(e2)[:700]

                    combined = f"JUPITER: {jup_err} | RAYDIUM: {ray_err}"
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
