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
        "trader_poll_sec": int(os.getenv("TRADER_POLL_SEC", "5")),
    }
