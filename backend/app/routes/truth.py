# backend/app/routes/truth.py
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Query, BackgroundTasks
from sqlalchemy import select, func, and_
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.models import Call, StrategyResult, Channel, TruthOhlcvCache
from app.workers.run_truth_job import run_truth_job, MAX_HOLD_SEC

router = APIRouter(prefix="/truth", tags=["truth"])


@router.get("/pending")
def truth_pending(
    channel_key: str | None = Query(default=None),
    strategy_key: str = Query(default="tp35_sl20"),
):
    with SessionLocal() as db:  # type: Session
        q = (
            select(func.count())
            .select_from(StrategyResult)
            .join(Call, Call.id == StrategyResult.call_id)
            .where(StrategyResult.strategy_key == strategy_key)
            .where(Call.status == "DONE")
            .where(StrategyResult.truth_checked_at.is_(None))
        )
        if channel_key:
            q = q.join(Channel, Channel.id == Call.channel_id).where(Channel.key == channel_key)

        n = db.execute(q).scalar_one()
        return {
            "channel_key": channel_key,
            "strategy_key": strategy_key,
            "pending": int(n),
            "asof": datetime.now(timezone.utc).isoformat(),
        }


@router.get("/cache_status")
def truth_cache_status(
    channel_key: str | None = Query(default=None),
    timeframe: str = Query(default="second"),  # "second"|"minute"
):
    with SessionLocal() as db:  # type: Session
        base = (
            select(
                func.count().label("total_calls"),
                func.count(TruthOhlcvCache.id).label("cached_rows"),
                func.count().filter(TruthOhlcvCache.error.is_not(None)).label("cached_error_rows"),
            )
            .select_from(Call)
            .join(Channel, Channel.id == Call.channel_id)
            .outerjoin(
                TruthOhlcvCache,
                and_(
                    TruthOhlcvCache.call_id == Call.id,
                    TruthOhlcvCache.timeframe == timeframe,
                    TruthOhlcvCache.aggregate == 1,
                ),
            )
            .where(Call.status == "DONE")
        )

        if channel_key:
            base = base.where(Channel.key == channel_key)

        row = db.execute(base).one()
        total_calls = int(row.total_calls)
        cached_rows = int(row.cached_rows)
        cached_error_rows = int(row.cached_error_rows)

        return {
            "channel_key": channel_key,
            "timeframe": timeframe,
            "total_calls": total_calls,
            "cached_ok": max(0, cached_rows - cached_error_rows),
            "cached_error": cached_error_rows,
            "uncached": max(0, total_calls - cached_rows),
            "asof": datetime.now(timezone.utc).isoformat(),
        }


@router.post("/run")
def truth_run(
    background_tasks: BackgroundTasks,
    channel_key: str | None = Query(default=None),
    strategy_key: str = Query(default="tp35_sl20"),
    limit: int = Query(default=50, ge=1, le=500),
    sleep_s: float = Query(default=0.25, ge=0, le=5),
    prefer_seconds: bool = Query(default=True),
    max_hold_sec: int = Query(default=MAX_HOLD_SEC, ge=60, le=60 * 60),
):
    """
    Trigger a small batch Truth Job run.
    Uses cache-first behavior in the worker.
    """
    background_tasks.add_task(
        run_truth_job,
        channel_key=channel_key,
        strategy_key=strategy_key,
        limit=limit,
        sleep_s=sleep_s,
        prefer_seconds=prefer_seconds,
        max_hold_sec=max_hold_sec,
    )
    return {
        "queued": True,
        "channel_key": channel_key,
        "strategy_key": strategy_key,
        "limit": limit,
        "sleep_s": sleep_s,
        "prefer_seconds": prefer_seconds,
        "max_hold_sec": max_hold_sec,
    }


@router.post("/cache_backfill")
def truth_cache_backfill(
    background_tasks: BackgroundTasks,
    channel_key: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=500),
    sleep_s: float = Query(default=0.25, ge=0, le=5),
    max_hold_sec: int = Query(default=MAX_HOLD_SEC, ge=60, le=60 * 60),
):
    """
    Warm cache only by running truth job with prefer_seconds True but strategy evaluation doesn't matter.
    We'll simply call run_truth_job using a dummy strategy_key that exists; it will fill caches as it goes.
    """
    background_tasks.add_task(
        run_truth_job,
        channel_key=channel_key,
        strategy_key="tp35_sl20",
        limit=limit,
        sleep_s=sleep_s,
        prefer_seconds=True,
        max_hold_sec=max_hold_sec,
    )
    return {
        "queued": True,
        "mode": "cache_backfill",
        "channel_key": channel_key,
        "limit": limit,
        "sleep_s": sleep_s,
        "max_hold_sec": max_hold_sec,
    }
