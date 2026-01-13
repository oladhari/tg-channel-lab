# backend/app/workers/run_buyer_live.py
from __future__ import annotations

import os
import time
import asyncio
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session
from sqlalchemy.exc import OperationalError

from app.db.session import SessionLocal
from app.models import Call

from app.executors.jup_executor import SOL_MINT, jup_swap_exact_in, sol_to_lamports
from app.executors.raydium_executor import raydium_swap_exact_in

LIVE_BUY_AMOUNT_SOL = float(os.getenv("LIVE_BUY_AMOUNT_SOL", "0.1"))
BUY_POLL_SEC = int(os.getenv("BUYER_POLL_SEC", "2"))
BUY_COOLDOWN_SEC = int(os.getenv("LIVE_BUY_COOLDOWN_SEC", "15"))

# slippage ladder (bps)
SLIPPAGE_STEPS_BPS = [
    int(x) for x in os.getenv("LIVE_SLIPPAGE_STEPS_BPS", "2500,5000,10000,20000").split(",")
]

_last_sent: dict[int, float] = {}  # call_id -> ts


def pick_ready_calls(db: Session) -> list[Call]:
    c = Call
    stmt = (
        select(c)
        .where(c.live_buy_enabled == True)  # noqa: E712
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
        except OperationalError:
            if time.time() - start > max_wait_sec:
                raise
            await asyncio.sleep(2)


def _mark(
    db: Session,
    call: Call,
    *,
    status: str,
    method: str | None = None,
    tx: str | None = None,
    err: str | None = None,
    amount: float | None = None,
) -> None:
    call.live_buy_status = status
    call.live_buy_sent_at = datetime.now(timezone.utc)
    call.live_buy_error = (err or None)
    call.live_buy_amount_sol = float(amount or call.live_buy_amount_sol or LIVE_BUY_AMOUNT_SOL)

    # keep compatibility if columns exist / not exist
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
            sig, _quote = jup_swap_exact_in(
                input_mint=SOL_MINT,
                output_mint=mint,
                in_amount_raw=in_amount_raw,
                slippage_bps=bps,
                wrap_and_unwrap_sol=True,
            )
            return str(sig)
        except Exception as e:
            last_err = e
            continue

    raise RuntimeError(f"Jupiter buy failed: {last_err}")


def try_raydium_buy(mint: str, amount_sol: float) -> str:
    in_amount_raw = sol_to_lamports(amount_sol)
    last_err: Exception | None = None

    for bps in SLIPPAGE_STEPS_BPS:
        try:
            sigs, _resp = raydium_swap_exact_in(
                input_mint=SOL_MINT,
                output_mint=mint,
                in_amount_raw=in_amount_raw,
                slippage_bps=bps,
                wrap_and_unwrap_sol=True,
            )
            return str(sigs[0]) if sigs else "RAYDIUM_NO_SIG"
        except Exception as e:
            last_err = e
            continue

    raise RuntimeError(f"Raydium buy failed: {last_err}")


async def loop() -> None:
    print(
        f"[BUYER_LIVE] starting | poll={BUY_POLL_SEC}s cooldown={BUY_COOLDOWN_SEC}s amount={LIVE_BUY_AMOUNT_SOL} SOL"
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

                amount = float(call.live_buy_amount_sol or LIVE_BUY_AMOUNT_SOL)

                try:
                    # 1) Jupiter
                    tx = try_jupiter_buy(call.mint, amount)
                    _mark(db, call, status="SENT", method="JUPITER", tx=tx, amount=amount)
                    _last_sent[call.id] = now
                    print(f"[BUYER_LIVE][JUP OK] call_id={call.id} {call.mint[:8]}... amount={amount} tx={tx}")

                except Exception as e1:
                    try:
                        # 2) Raydium fallback
                        tx = try_raydium_buy(call.mint, amount)
                        _mark(db, call, status="SENT", method="RAYDIUM", tx=tx, amount=amount)
                        _last_sent[call.id] = now
                        print(f"[BUYER_LIVE][RAY OK] call_id={call.id} {call.mint[:8]}... amount={amount} tx={tx}")

                    except Exception as e2:
                        # 3) Mark for GMGN fallback buyer to pick up
                        # IMPORTANT: GMGN buyer should accept BOTH "NONE" and "FALLBACK_GMGN"
                        _mark(
                            db,
                            call,
                            status="FALLBACK_GMGN",
                            method="AUTO_FAIL",
                            err=str(e2)[:300],
                            amount=amount,
                        )
                        _last_sent[call.id] = now
                        print(f"[BUYER_LIVE][AUTO FAIL] call_id={call.id} -> FALLBACK_GMGN err={e2}")

        finally:
            db.close()

        await asyncio.sleep(BUY_POLL_SEC)


def main() -> None:
    asyncio.run(loop())


if __name__ == "__main__":
    main()
