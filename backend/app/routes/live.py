# backend/app/routes/live.py
from __future__ import annotations

from fastapi import APIRouter, Query
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
    strategy_key: str = Query(default="tp35_sl20"),
):
    """
    Show calls that are live-sell enabled and their current live sell status.

    NOTE: strategy_key is optional join (so you can see TP/SL/TIME outcome if already computed).
    """
    db: Session = SessionLocal()
    try:
        c, ch, sr = Call, Channel, StrategyResult

        stmt = (
            select(
                c.id,
                ch.key.label("channel_key"),
                ch.telegram_username,
                c.mint,
                c.symbol,
                c.status,
                c.started_at,
                c.entry_price_usd,
                c.duration_sec,
                c.live_buy_status,
                c.live_buy_sent_at,
                c.live_buy_amount_sol,
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
            .outerjoin(sr, (sr.call_id == c.id) & (sr.strategy_key == strategy_key))
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
            select(ch.id, ch.key, ch.telegram_username, ch.live_buy_amount_sol)
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
