# backend/app/routes/live.py
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.models import Call, Channel, StrategyResult

router = APIRouter(prefix="/live", tags=["live"])


@router.get("/queue")
def live_queue(
    limit: int = Query(default=200, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    channel_key: str | None = None,
    sell_status: str | None = None,  # NONE | SENT | ERROR
):
    """
    Show calls that are live-sell enabled and their current live sell status.
    Joins the first StrategyResult per call (by id) to show the actual TP/SL
    thresholds that were active during recording.
    """
    from sqlalchemy import func

    db: Session = SessionLocal()
    try:
        c, ch, sr = Call, Channel, StrategyResult

        # Subquery: pick the lowest (first-written) StrategyResult id per call
        sr_first = (
            select(
                func.min(sr.id).label("min_sr_id"),
                sr.call_id.label("call_id"),
            )
            .group_by(sr.call_id)
            .subquery("sr_first")
        )

        stmt = (
            select(
                c.id,
                ch.key.label("channel_key"),
                ch.telegram_username,
                ch.live_tp_pct,
                ch.live_sl_pct,
                c.mint,
                c.symbol,
                c.status,
                c.started_at,
                c.entry_price_usd,
                c.duration_sec,
                c.live_buy_status,
                c.live_buy_sent_at,
                c.live_buy_amount_sol,
                ch.live_buy_amount_sol.label("channel_buy_amount_sol"),
                c.live_buy_error,
                c.live_sell_enabled,
                c.live_sell_status,
                c.live_sell_reason,
                c.live_sell_sent_at,
                c.live_sell_error,
                sr.strategy_key,
                sr.outcome,
                sr.pnl_pct,
                sr.exit_t_sec,
                sr.exit_price_usd,
            )
            .join(ch, ch.id == c.channel_id)
            .outerjoin(sr_first, sr_first.c.call_id == c.id)
            .outerjoin(sr, sr.id == sr_first.c.min_sr_id)
            .where(c.live_sell_enabled == True)  # noqa: E712
            .order_by(c.started_at.desc())
            .limit(limit)
            .offset(offset)
        )

        if channel_key:
            stmt = stmt.where(ch.key == channel_key)

        if sell_status:
            stmt = stmt.where(c.live_sell_status == sell_status)

        rows = db.execute(stmt).all()
        return [dict(r._mapping) for r in rows]
    finally:
        db.close()


@router.get("/wallet")
def live_wallet():
    """Wallet SOL balance + live trade stats from the bot."""
    import os
    import json
    import requests as req

    rpc_url = os.getenv("SOLANA_RPC_URL", "https://api.mainnet-beta.solana.com")
    raw_key = os.getenv("SOLANA_PRIVATE_KEY", "").strip()

    pubkey: str | None = None
    sol_balance: float | None = None

    if raw_key:
        try:
            from solders.keypair import Keypair  # type: ignore

            if raw_key.startswith("["):
                kp = Keypair.from_bytes(bytes(json.loads(raw_key)))
            else:
                import base58  # type: ignore
                kp = Keypair.from_bytes(base58.b58decode(raw_key))
            pubkey = str(kp.pubkey())

            resp = req.post(
                rpc_url,
                json={"jsonrpc": "2.0", "id": 1, "method": "getBalance", "params": [pubkey]},
                timeout=5,
            )
            lamports = resp.json().get("result", {}).get("value", 0)
            sol_balance = round(lamports / 1_000_000_000, 4)
        except Exception:
            pass

    db: Session = SessionLocal()
    try:
        from sqlalchemy import func

        c, ch = Call, Channel

        total_buys = db.execute(
            select(func.count()).where(c.live_buy_status != "NONE")
        ).scalar() or 0

        total_sells = db.execute(
            select(func.count()).where(c.live_sell_status == "SENT")
        ).scalar() or 0

        # Bought but sell not yet triggered
        holding = db.execute(
            select(func.count()).where(
                (c.live_buy_status == "SENT") & (c.live_sell_status == "NONE")
            )
        ).scalar() or 0

        live_channels = db.execute(
            select(ch.id, ch.key, ch.telegram_username, ch.live_buy_amount_sol, ch.live_tp_pct, ch.live_sl_pct)
            .where(ch.live_enabled == True)  # noqa: E712
            .order_by(ch.key)
        ).all()

        return {
            "pubkey": pubkey,
            "sol_balance": sol_balance,
            "total_buys": total_buys,
            "total_sells": total_sells,
            "holding": holding,
            "live_channels": [dict(r._mapping) for r in live_channels],
        }
    finally:
        db.close()


@router.post("/calls/{call_id}/mark-sold")
def mark_sold(call_id: int):
    """Mark a call as manually sold (sets live_sell_status=SENT so it leaves Holding view)."""
    db: Session = SessionLocal()
    try:
        call = db.get(Call, call_id)
        if not call:
            raise HTTPException(status_code=404, detail="Call not found")
        call.live_sell_status = "SENT"
        call.live_sell_sent_at = datetime.now(timezone.utc)
        db.commit()
        return {"ok": True, "call_id": call_id}
    finally:
        db.close()


@router.get("/wallet-history")
def wallet_history(limit: int = Query(default=50, ge=1, le=100)):
    """
    Fetch on-chain swap history using the free Solana RPC (no API key needed).

    Flow:
      1. getSignaturesForAddress  — list recent tx signatures
      2. getTransaction (jsonParsed) — parse token balance changes per tx
      3. Determine BUY / SELL from wallet's token balance delta vs SOL delta
      4. Cross-reference found mints against our DB calls
    """
    import os
    import json
    import requests as req

    raw_key = os.getenv("SOLANA_PRIVATE_KEY", "").strip()
    rpc_url = os.getenv("SOLANA_RPC_URL", "https://api.mainnet-beta.solana.com")

    pubkey: str | None = None
    if raw_key:
        try:
            from solders.keypair import Keypair  # type: ignore
            if raw_key.startswith("["):
                kp = Keypair.from_bytes(bytes(json.loads(raw_key)))
            else:
                import base58  # type: ignore
                kp = Keypair.from_bytes(base58.b58decode(raw_key))
            pubkey = str(kp.pubkey())
        except Exception:
            pass

    if not pubkey:
        return {"error": "Could not derive wallet pubkey (SOLANA_PRIVATE_KEY not set)", "trades": [], "pubkey": None}

    def rpc(method: str, params: list) -> dict:
        r = req.post(rpc_url, json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params}, timeout=10)
        r.raise_for_status()
        return r.json()

    # Step 1 — get signature list
    try:
        sig_resp = rpc("getSignaturesForAddress", [pubkey, {"limit": limit, "commitment": "finalized"}])
    except Exception as e:
        return {"error": f"getSignaturesForAddress failed: {e}", "trades": [], "pubkey": pubkey}

    signatures = [s["signature"] for s in (sig_resp.get("result") or []) if not s.get("err")]

    # Step 2 — fetch + parse each transaction
    WSOL = "So11111111111111111111111111111111111111112"
    trades: list[dict] = []
    mints_seen: set[str] = set()

    for sig in signatures:
        try:
            tx_resp = rpc("getTransaction", [sig, {"encoding": "jsonParsed", "maxSupportedTransactionVersion": 0, "commitment": "finalized"}])
        except Exception:
            continue

        result = tx_resp.get("result")
        if not result:
            continue

        meta = result.get("meta") or {}
        block_time = result.get("blockTime")

        pre_tok: list[dict] = meta.get("preTokenBalances") or []
        post_tok: list[dict] = meta.get("postTokenBalances") or []
        pre_sol: list[int] = meta.get("preBalances") or []
        post_sol: list[int] = meta.get("postBalances") or []

        # Find wallet's account index from the account keys
        account_keys = []
        try:
            tx_msg = result.get("transaction", {}).get("message", {})
            account_keys = [a.get("pubkey") or a for a in tx_msg.get("accountKeys", [])]
        except Exception:
            pass

        wallet_idx: int | None = None
        try:
            wallet_idx = account_keys.index(pubkey)
        except ValueError:
            pass

        # SOL change for our wallet account
        sol_delta: float | None = None
        if wallet_idx is not None and wallet_idx < len(pre_sol) and wallet_idx < len(post_sol):
            sol_delta = round((post_sol[wallet_idx] - pre_sol[wallet_idx]) / 1e9, 6)

        # Build token balance maps keyed by mint for wallet-owned accounts
        def tok_map(balances: list[dict]) -> dict[str, float]:
            m: dict[str, float] = {}
            for b in balances:
                if b.get("owner") != pubkey:
                    continue
                mint_addr = b.get("mint", "")
                if mint_addr == WSOL:
                    continue
                amt = (b.get("uiTokenAmount") or {}).get("uiAmount") or 0.0
                m[mint_addr] = float(amt)
            return m

        pre_map = tok_map(pre_tok)
        post_map = tok_map(post_tok)

        all_mints = set(pre_map) | set(post_map)
        # Filter out SOL/WSOL, look for the token that changed most
        token_deltas = {
            m: post_map.get(m, 0.0) - pre_map.get(m, 0.0)
            for m in all_mints
        }

        if not token_deltas:
            continue  # no wallet-owned token change — skip

        # Pick mint with largest absolute change
        main_mint = max(token_deltas, key=lambda m: abs(token_deltas[m]))
        tok_delta = token_deltas[main_mint]

        if tok_delta == 0:
            continue

        # Classify direction
        if tok_delta > 0 and (sol_delta is None or sol_delta <= 0):
            direction = "BUY"
            sol_amount = abs(sol_delta) if sol_delta is not None else None
        elif tok_delta < 0 and (sol_delta is None or sol_delta >= 0):
            direction = "SELL"
            sol_amount = abs(sol_delta) if sol_delta is not None else None
        else:
            direction = "SWAP"
            sol_amount = None

        mints_seen.add(main_mint)
        trades.append({
            "signature": sig,
            "timestamp": block_time,
            "direction": direction,
            "mint": main_mint,
            "sol_amount": sol_amount,
            "token_amount": round(abs(tok_delta), 4),
            "dex": "",
            "description": "",
        })

    # Step 3 — cross-reference with our DB calls by mint + reconcile untracked sells
    import os as _os
    from sqlalchemy import func as _func

    db: Session = SessionLocal()
    try:
        if mints_seen:
            db_calls = db.execute(
                select(
                    Call.id,
                    Call.mint,
                    Call.symbol,
                    Call.started_at,
                    Call.entry_price_usd,
                    Call.live_buy_status,
                    Call.live_sell_status,
                    Call.live_sell_reason,
                    Call.live_buy_amount_sol,
                    StrategyResult.strategy_key,
                    StrategyResult.outcome,
                    StrategyResult.pnl_pct,
                    StrategyResult.exit_price_usd,
                )
                .outerjoin(StrategyResult, StrategyResult.call_id == Call.id)
                .where(Call.mint.in_(list(mints_seen)))
                .where(Call.live_sell_enabled == True)  # noqa: E712
                .order_by(StrategyResult.id.asc())
            ).all()

            mint_to_call: dict[str, dict] = {}
            for row in db_calls:
                m = row.mint
                if m not in mint_to_call:
                    mint_to_call[m] = dict(row._mapping)

            for t in trades:
                t["call"] = mint_to_call.get(t["mint"])

            # Reconcile: real on-chain SELL found but DB still shows NONE
            live_strategy_key = _os.getenv("LIVE_STRATEGY_KEY", "tp35_sl20")
            for t in trades:
                call_data = t.get("call")
                if (
                    t["direction"] == "SELL"
                    and call_data is not None
                    and call_data.get("live_sell_status") == "NONE"
                ):
                    call_obj = db.get(Call, call_data["id"])
                    if call_obj is None:
                        continue

                    # Mark sell as completed
                    call_obj.live_sell_status = "SENT"
                    sell_ts = t.get("timestamp")
                    if sell_ts:
                        call_obj.live_sell_sent_at = datetime.fromtimestamp(sell_ts, tz=timezone.utc)
                    call_obj.live_sell_reason = "REAL_SELL"

                    # Create StrategyResult if none exists for this call
                    existing_sr = db.execute(
                        select(StrategyResult).where(StrategyResult.call_id == call_obj.id)
                    ).scalars().first()

                    if existing_sr is None:
                        buy_sol = call_obj.live_buy_amount_sol or 0.0
                        sell_sol = t.get("sol_amount") or 0.0
                        entry_px = call_obj.entry_price_usd or 0.0

                        if buy_sol > 0 and sell_sol > 0:
                            pnl_pct = round((sell_sol - buy_sol) / buy_sol * 100, 4)
                        else:
                            pnl_pct = 0.0

                        exit_px = round(entry_px * (1 + pnl_pct / 100), 10) if entry_px else 0.0
                        outcome = "TP" if pnl_pct >= 0 else "SL"

                        started_ts = call_obj.started_at.timestamp() if call_obj.started_at else 0
                        exit_t = int(sell_ts - started_ts) if sell_ts else 0

                        sr = StrategyResult(
                            call_id=call_obj.id,
                            strategy_key=live_strategy_key,
                            tp_pct=0.0,
                            sl_pct=0.0,
                            entry_price_usd=entry_px,
                            exit_price_usd=exit_px,
                            exit_t_sec=max(0, exit_t),
                            outcome=outcome,
                            pnl_pct=pnl_pct,
                        )
                        db.add(sr)

                    try:
                        db.commit()
                    except Exception:
                        # Another concurrent request already reconciled this call — safe to ignore
                        db.rollback()

                    # Update the trade's call snapshot to reflect new state
                    call_data["live_sell_status"] = "SENT"
                    call_data["live_sell_reason"] = "REAL_SELL"
        else:
            for t in trades:
                t["call"] = None
    finally:
        db.close()

    return {"pubkey": pubkey, "trades": trades, "error": None}


@router.get("/config")
def live_config():
    """
    Minimal config surface for UI (non-secret).
    """
    import os

    return {
        "gmgn_target_set": bool(os.getenv("GMGN_TARGET", "").strip()),
        "gmgn_sell_percent": os.getenv("GMGN_SELL_PERCENT", "100%").strip(),
        "live_strategy_key": os.getenv("LIVE_STRATEGY_KEY", "tp35_sl20").strip(),
        "trader_poll_sec": int(os.getenv("TRADER_POLL_SEC", "2")),
    }
