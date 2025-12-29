from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.models import Call, Channel, PricePoint, StrategyResult

router = APIRouter(prefix="/calls", tags=["calls"])


@router.get("")
def list_calls(
    limit: int = Query(default=200, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    strategy_key: str = Query(default="tp35_sl20"),
    channel_key: Optional[str] = None,
    status: Optional[str] = None,
):
    """
    Latest calls list with:
    - channel_key joined
    - ONE joined StrategyResult for requested strategy_key (default tp35_sl20)
    """
    db: Session = SessionLocal()
    try:
        c, ch, sr = Call, Channel, StrategyResult

        stmt = (
            select(
                c.id,
                c.channel_id,
                ch.key.label("channel_key"),
                c.mint,
                c.symbol,
                c.status,
                c.started_at,
                c.duration_sec,
                c.entry_price_usd,
                c.ignore_reason,
                sr.strategy_key,
                sr.outcome,
                sr.pnl_pct,
                sr.exit_t_sec,
                sr.exit_price_usd,
            )
            .join(ch, ch.id == c.channel_id)
            .outerjoin(sr, (sr.call_id == c.id) & (sr.strategy_key == strategy_key))
            .order_by(c.started_at.desc())
            .limit(limit)
            .offset(offset)
        )

        if channel_key:
            stmt = stmt.where(ch.key == channel_key)
        if status:
            stmt = stmt.where(c.status == status)

        rows = db.execute(stmt).all()
        return [dict(r._mapping) for r in rows]
    finally:
        db.close()


@router.get("/{call_id}")
def get_call(call_id: int):
    db: Session = SessionLocal()
    try:
        call = db.query(Call).filter(Call.id == call_id).one_or_none()
        if not call:
            raise HTTPException(status_code=404, detail="Call not found")

        ch = db.query(Channel).filter(Channel.id == call.channel_id).one_or_none()
        channel_key = ch.key if ch else "unknown"

        srs = (
            db.query(StrategyResult)
            .filter(StrategyResult.call_id == call_id)
            .order_by(StrategyResult.strategy_key.asc())
            .all()
        )

        return {
            "id": call.id,
            "channel_id": call.channel_id,
            "channel_key": channel_key,
            "mint": call.mint,
            "symbol": call.symbol,
            "status": call.status,
            "started_at": call.started_at,
            "duration_sec": call.duration_sec,
            "entry_price_usd": call.entry_price_usd,
            "ignore_reason": call.ignore_reason,
            "strategy_results": [
                {
                    "strategy_key": x.strategy_key,
                    "tp_pct": x.tp_pct,
                    "sl_pct": x.sl_pct,
                    "entry_price_usd": x.entry_price_usd,
                    "exit_price_usd": x.exit_price_usd,
                    "exit_t_sec": x.exit_t_sec,
                    "outcome": x.outcome,
                    "pnl_pct": x.pnl_pct,
                }
                for x in srs
            ],
        }
    finally:
        db.close()


@router.get("/{call_id}/prices")
def get_call_prices(call_id: int):
    db: Session = SessionLocal()
    try:
        call = db.query(Call).filter(Call.id == call_id).one_or_none()
        if not call:
            raise HTTPException(status_code=404, detail="Call not found")

        pts = (
            db.query(PricePoint.t_sec, PricePoint.price_usd)
            .filter(PricePoint.call_id == call_id)
            .order_by(PricePoint.t_sec.asc())
            .all()
        )

        return [{"t_sec": int(t), "price_usd": float(p)} for (t, p) in pts]
    finally:
        db.close()
