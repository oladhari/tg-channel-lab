# backend/app/workers/run_buyer_live.py
from __future__ import annotations

import os
import time
import asyncio
from datetime import datetime, timezone

import requests
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload
from sqlalchemy.exc import OperationalError

from app.db.session import SessionLocal
from app.models import Call, Channel

from app.executors.jup_executor import SOL_MINT, jup_swap_exact_in, sol_to_lamports
from app.executors.raydium_executor import raydium_swap_exact_in

# Only used if call+channel missing (should be rare)
LIVE_BUY_AMOUNT_SOL = float(os.getenv("LIVE_BUY_AMOUNT_SOL", "0.1"))

BUY_POLL_SEC = int(os.getenv("BUYER_POLL_SEC", "2"))
BUY_COOLDOWN_SEC = int(os.getenv("LIVE_BUY_COOLDOWN_SEC", "15"))

# aggressive knobs
RPC_URL = os.getenv("SOLANA_RPC_URL", "https://api.mainnet-beta.solana.com").strip()
LIVE_CONFIRM_MS = int(os.getenv("LIVE_CONFIRM_MS", "1200"))
LIVE_FAST_MODE = os.getenv("LIVE_FAST_MODE", "1").strip() not in ("0", "false", "False")

# slippage ladder (bps)
SLIPPAGE_STEPS_BPS = [int(x) for x in os.getenv("LIVE_SLIPPAGE_STEPS_BPS", "2500,5000,10000,20000").split(",")]

# Raydium compute endpoint rejects large bps → clamp for Raydium
RAYDIUM_MAX_BPS = int(os.getenv("RAYDIUM_MAX_SLIPPAGE_BPS", "5000"))
SLIPPAGE_STEPS_BPS_RAYDIUM = sorted({min(int(x), RAYDIUM_MAX_BPS) for x in SLIPPAGE_STEPS_BPS if int(x) > 0})

_last_sent: dict[int, float] = {}  # call_id -> ts


def _get_sig_status(sig: str) -> str | None:
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
        return None
    return v.get("confirmationStatus") or None


def _confirm_fast(sig: str, max_ms: int) -> bool:
    deadline = time.time() + (max_ms / 1000.0)
    while time.time() < deadline:
        try:
            st = _get_sig_status(sig)
            if st in ("processed", "confirmed", "finalized"):
                return True
        except Exception:
            pass
        time.sleep(0.10)
    return False


def _resolve_amount(call: Call) -> tuple[float, str, dict]:
    """
    Source of truth:
      1) call.live_buy_amount_sol (ONLY if explicitly set as per-call override)
      2) call.channel.live_buy_amount_sol (UI value)
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


def pick_ready_calls(db: Session) -> list[Call]:
    c = Call
    ch = Channel

    stmt = (
        select(c)
        .join(ch, ch.id == c.channel_id)
        .options(joinedload(c.channel))
        .where(ch.live_enabled == True)          # ✅ keep your condition
        .where(c.live_buy_enabled == True)
        .where(c.live_buy_status == "NONE")
        .where(c.status == "RECORDING")
        .where(c.entry_price_usd.isnot(None))
        .order_by(c.started_at.asc())
        .limit(50)
    )
    return list(db.execute(stmt).scalars().all())


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
            print(f"[BUYER_LIVE][DB RETRY] err={str(e)[:200]}", flush=True)
            await asyncio.sleep(2)


def _mark(
    db: Session,
    call: Call,
    *,
    status: str,
    method: str | None = None,
    tx: str | None = None,
    err: str | None = None,
    amount_used: float | None = None,
) -> None:
    call.live_buy_status = status
    call.live_buy_sent_at = datetime.now(timezone.utc)
    call.live_buy_error = (err or None)

    # For auditing, snapshot the amount that was actually used when SENT.
    # But do NOT "lock" calls on fallback.
    if amount_used is not None and status == "SENT":
        call.live_buy_amount_sol = float(amount_used)

    # optional columns if you add them later
    if hasattr(call, "live_buy_method"):
        call.live_buy_method = method
    if hasattr(call, "live_buy_tx_sig"):
        call.live_buy_tx_sig = tx

    db.add(call)
    db.commit()


def try_jupiter_buy(mint: str, amount_sol: float) -> str:
    in_amount_raw = sol_to_lamports(amount_sol)
    last_err: Exception | None = None

    for bps in SLIPPAGE_STEPS_BPS:
        try:
            print(f"[BUYER_LIVE][JUP TRY] mint={mint[:8]}... bps={bps} amount={amount_sol} fast={LIVE_FAST_MODE}", flush=True)
            sig, _quote = jup_swap_exact_in(
                input_mint=SOL_MINT,
                output_mint=mint,
                in_amount_raw=in_amount_raw,
                slippage_bps=bps,
                wrap_and_unwrap_sol=True,
                fast_mode=LIVE_FAST_MODE,
            )
            return str(sig)
        except Exception as e:
            last_err = e
            print(f"[BUYER_LIVE][JUP FAIL] mint={mint[:8]}... bps={bps} err={str(e)[:500]}", flush=True)
            continue

    raise RuntimeError(f"Jupiter buy failed: {last_err}")


def try_raydium_buy(mint: str, amount_sol: float) -> str:
    in_amount_raw = sol_to_lamports(amount_sol)
    last_err: Exception | None = None

    for bps in SLIPPAGE_STEPS_BPS_RAYDIUM:
        try:
            print(f"[BUYER_LIVE][RAY TRY] mint={mint[:8]}... bps={bps} amount={amount_sol} fast={LIVE_FAST_MODE}", flush=True)
            sigs, _resp = raydium_swap_exact_in(
                input_mint=SOL_MINT,
                output_mint=mint,
                in_amount_raw=in_amount_raw,
                slippage_bps=bps,
                wrap_and_unwrap_sol=True,
                fast_mode=LIVE_FAST_MODE,
            )
            return str(sigs[0]) if sigs else "RAYDIUM_NO_SIG"
        except Exception as e:
            last_err = e
            print(f"[BUYER_LIVE][RAY FAIL] mint={mint[:8]}... bps={bps} err={str(e)[:500]}", flush=True)
            continue

    raise RuntimeError(f"Raydium buy failed: {last_err}")


async def loop() -> None:
    print(
        f"[BUYER_LIVE] starting | poll={BUY_POLL_SEC}s cooldown={BUY_COOLDOWN_SEC}s "
        f"env_default_amount={LIVE_BUY_AMOUNT_SOL} SOL (actual resolved per call) "
        f"| fast={LIVE_FAST_MODE} confirm_ms={LIVE_CONFIRM_MS} rpc={RPC_URL}",
        flush=True,
    )
    print(f"[BUYER_LIVE] slippage_jup_bps={SLIPPAGE_STEPS_BPS}", flush=True)
    print(f"[BUYER_LIVE] slippage_raydium_bps={SLIPPAGE_STEPS_BPS_RAYDIUM} (max={RAYDIUM_MAX_BPS})", flush=True)
    print(
        "[BUYER_LIVE] jupiter_priority:"
        f" maxLamports={os.getenv('JUP_MAX_PRIORITY_FEE_LAMPORTS','1000000')}"
        f" level={os.getenv('JUP_PRIORITY_LEVEL','veryHigh')}",
        flush=True,
    )

    while True:
        db = await open_db_retry()
        try:
            calls = pick_ready_calls(db)

            for call in calls:
                now = time.time()
                last = _last_sent.get(call.id, 0.0)
                if now - last < BUY_COOLDOWN_SEC:
                    continue

                amount, src, dbg = _resolve_amount(call)
                print(
                    "[BUYER_LIVE][PICK] "
                    f"call_id={call.id} mint={call.mint[:8]}... "
                    f"resolved_amount={amount} source={src} "
                    f"call_amount={dbg['call_amount']} channel_amount={dbg['channel_amount']} "
                    f"env_default={dbg['env_default']} channel_loaded={dbg['channel_loaded']}",
                    flush=True,
                )

                jup_err: str | None = None
                ray_err: str | None = None

                # 1) Jupiter (fast)
                try:
                    tx = try_jupiter_buy(call.mint, amount)
                    ok = _confirm_fast(tx, LIVE_CONFIRM_MS)
                    if ok:
                        _mark(db, call, status="SENT", method="JUPITER", tx=tx, amount_used=amount)
                        _last_sent[call.id] = now
                        print(f"[BUYER_LIVE][JUP OK] call_id={call.id} tx={tx}", flush=True)
                        continue

                    # Not seen quickly -> aggressive fallback
                    _mark(
                        db,
                        call,
                        status="FALLBACK_GMGN",
                        method="JUP_TIMEOUT",
                        err=f"JUP sig not seen within {LIVE_CONFIRM_MS}ms (tx={tx})",
                        amount_used=None,
                    )
                    _last_sent[call.id] = now
                    print(f"[BUYER_LIVE][JUP TIMEOUT] call_id={call.id} -> FALLBACK_GMGN tx={tx}", flush=True)
                    continue

                except Exception as e1:
                    jup_err = str(e1)[:700]
                    print(f"[BUYER_LIVE][JUP TOTAL FAIL] call_id={call.id} err={jup_err}", flush=True)

                # 2) Raydium (fast)
                try:
                    tx = try_raydium_buy(call.mint, amount)
                    ok = (tx != "RAYDIUM_NO_SIG") and _confirm_fast(tx, LIVE_CONFIRM_MS)
                    if ok:
                        _mark(db, call, status="SENT", method="RAYDIUM", tx=tx, amount_used=amount)
                        _last_sent[call.id] = now
                        print(f"[BUYER_LIVE][RAY OK] call_id={call.id} tx={tx}", flush=True)
                        continue

                    _mark(
                        db,
                        call,
                        status="FALLBACK_GMGN",
                        method="RAY_TIMEOUT",
                        err=f"RAY sig not seen within {LIVE_CONFIRM_MS}ms (tx={tx})",
                        amount_used=None,
                    )
                    _last_sent[call.id] = now
                    print(f"[BUYER_LIVE][RAY TIMEOUT] call_id={call.id} -> FALLBACK_GMGN tx={tx}", flush=True)
                    continue

                except Exception as e2:
                    ray_err = str(e2)[:700]

                combined = f"JUPITER: {jup_err} | RAYDIUM: {ray_err}"
                _mark(
                    db,
                    call,
                    status="FALLBACK_GMGN",
                    method="AUTO_FAIL",
                    err=combined[:900],
                    amount_used=None,  # don't lock amount on fallback
                )
                _last_sent[call.id] = now
                print(f"[BUYER_LIVE][AUTO FAIL] call_id={call.id} -> FALLBACK_GMGN", flush=True)
                print(f"[BUYER_LIVE][AUTO FAIL][DETAIL] {combined[:900]}", flush=True)

        except Exception as fatal:
            print(f"[BUYER_LIVE][FATAL] loop exception: {fatal}", flush=True)
            raise
        finally:
            db.close()

        await asyncio.sleep(BUY_POLL_SEC)


def main() -> None:
    asyncio.run(loop())


if __name__ == "__main__":
    main()
