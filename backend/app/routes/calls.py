# backend/app/routes/calls.py
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
                # Live buy
                c.live_buy_status,
                c.live_buy_sent_at,
                c.live_buy_amount_sol,
                c.live_buy_error,
                # Live sell
                c.live_sell_status,
                c.live_sell_reason,
                c.live_sell_sent_at,
                c.live_sell_error,
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
            "raw_message": call.raw_message,
            "status": call.status,
            "started_at": call.started_at,
            "duration_sec": call.duration_sec,
            "entry_price_usd": call.entry_price_usd,
            "ignore_reason": call.ignore_reason,
            # Snapshot fields
            "snapshot_at": call.snapshot_at,
            "dex_id": call.dex_id,
            "pair_created_at_ms": call.pair_created_at_ms,
            "liquidity_usd": call.liquidity_usd,
            "market_cap": call.market_cap,
            "vol_m5": call.vol_m5,
            "vol_h1": call.vol_h1,
            "pc_m5": call.pc_m5,
            "pc_h1": call.pc_h1,
            "buys_m5": call.buys_m5,
            "sells_m5": call.sells_m5,
            "buys_h1": call.buys_h1,
            "sells_h1": call.sells_h1,
            # Live buy
            "live_buy_status": call.live_buy_status,
            "live_buy_sent_at": call.live_buy_sent_at,
            "live_buy_amount_sol": call.live_buy_amount_sol,
            "live_buy_error": call.live_buy_error,
            # Live sell
            "live_sell_status": call.live_sell_status,
            "live_sell_reason": call.live_sell_reason,
            "live_sell_sent_at": call.live_sell_sent_at,
            "live_sell_error": call.live_sell_error,
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
            .order_by(PricePoint.t_sec.asc(), PricePoint.id.asc())
            .all()
        )

        # Deduplicate by t_sec — burst mode (200ms) can produce multiple rows with the
        # same t_sec value. lightweight-charts requires strictly ascending timestamps,
        # so we keep only the LAST price recorded at each second.
        seen: dict[int, float] = {}
        for t, p in pts:
            seen[int(t)] = float(p)
        return [{"t_sec": k, "price_usd": v} for k, v in sorted(seen.items())]
    finally:
        db.close()
