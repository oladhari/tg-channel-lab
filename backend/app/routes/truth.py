# backend/app/routes/truth.py
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Query, BackgroundTasks, HTTPException
from sqlalchemy import select, func, and_
from sqlalchemy.orm import Session, selectinload

from app.db.session import SessionLocal
from app.models import Call, StrategyResult, Channel, TruthOhlcvCache
from app.schemas.stats import GridSimOut, GridCellOut  # reuse same schema as /stats/grid
from app.settings import settings
from app.workers.run_truth_job import run_truth_job, MAX_HOLD_SEC
from app.services.coingecko_onchain import CoinGeckoOnchainClient
from app.services.truth_cache import get_cache, fetch_and_store, load_cached_series

router = APIRouter(prefix="/truth", tags=["truth"])

# --- cache quality thresholds (tunable) ---
# seconds: for a 25min window we "expect" ~1501 points if dense.
# but some pools legitimately return sparse seconds.
MIN_SECONDS_POINTS = 300  # below this, fall back to minute
MIN_MINUTE_POINTS = 10    # sanity threshold


def _round2(x: float) -> float:
    return float(round(x, 2))


def _parse_csv_floats(s: str) -> list[float]:
    vals: list[float] = []
    for part in (s or "").split(","):
        part = part.strip()
        if not part:
            continue
        try:
            vals.append(float(part))
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid number in list: '{part}'")
    return sorted(set(vals))


def _sorted_rows(rows: list[list[float]]) -> list[list[float]]:
    clean = [r for r in rows if isinstance(r, list) and len(r) >= 6]
    clean.sort(key=lambda r: int(r[0]))
    return clean


def _pick_close_at_or_before(rows_sorted: list[list[float]], target_ts: int) -> float | None:
    close_px: float | None = None
    for r in rows_sorted:
        ts = int(r[0])
        if ts <= target_ts:
            close_px = float(r[4])
        else:
            break
    return close_px


def _evaluate_outcome_from_ohlcv(
    rows: list[list[float]],
    *,
    entry_price: float,
    tp_pct: float,
    sl_pct: float,
    entry_unix: int,
    max_hold_sec: int,
) -> tuple[str, float]:
    """
    Returns (outcome, pnl_pct):
      outcome: TP | SL | TIME_EXIT | AMBIGUOUS
      pnl_pct:
        TP => +tp_pct
        SL => -sl_pct
        TIME_EXIT => mark-to-close (exit/entry - 1) * 100
        AMBIGUOUS => 0.0  (we will SKIP ambiguous at aggregation level)
    """
    if entry_price <= 0:
        return ("TIME_EXIT", 0.0)

    tp_price = entry_price * (1.0 + tp_pct / 100.0)
    sl_price = entry_price * (1.0 - sl_pct / 100.0)

    rows_sorted = _sorted_rows(rows)
    target_ts = entry_unix + max_hold_sec

    for r in rows_sorted:
        ts, _o, h, l, c, _v = r
        ts = int(ts)
        if ts < entry_unix:
            continue
        if ts > target_ts:
            break

        high = float(h)
        low = float(l)

        hit_tp = high >= tp_price
        hit_sl = low <= sl_price

        if hit_tp and hit_sl:
            return ("AMBIGUOUS", 0.0)
        if hit_tp:
            return ("TP", float(tp_pct))
        if hit_sl:
            return ("SL", -float(sl_pct))

    close_px = _pick_close_at_or_before(rows_sorted, target_ts)
    if close_px is None or close_px <= 0:
        return ("TIME_EXIT", 0.0)

    pnl_pct = ((float(close_px) / float(entry_price)) - 1.0) * 100.0
    return ("TIME_EXIT", float(pnl_pct))


def _load_truth_series_for_call(
    db: Session,
    cg: CoinGeckoOnchainClient,
    *,
    call: Call,
    pool_address: str,
    dex_id: str,
    entry_unix: int,
    max_hold_sec: int,
    prefer_seconds: bool = True,
) -> tuple[str, list[list[float]]]:
    """
    Returns (source, rows) where source is:
      - "second_cache"
      - "minute_cache"
      - "minute_fetch"
      - "none"
    """

    # 1) seconds cache
    if prefer_seconds:
        sec_cache = get_cache(
            db,
            call_id=call.id,
            pool_address=pool_address,
            timeframe="second",
            aggregate=1,
        )
        if sec_cache and sec_cache.data_gz and not sec_cache.error:
            rows = load_cached_series(db, sec_cache)
            if len(rows) >= MIN_SECONDS_POINTS:
                return ("second_cache", rows)

    # 2) minute cache
    min_cache = get_cache(
        db,
        call_id=call.id,
        pool_address=pool_address,
        timeframe="minute",
        aggregate=1,
    )
    if min_cache and min_cache.data_gz and not min_cache.error:
        rows = load_cached_series(db, min_cache)
        if len(rows) >= MIN_MINUTE_POINTS:
            return ("minute_cache", rows)

    # 3) fetch minute once (ONLY if missing; keeps API usage small)
    before_ts = entry_unix + max_hold_sec + 120
    mc = fetch_and_store(
        db,
        cg=cg,
        call=call,
        pool=type("P", (), {"dex_id": dex_id, "pool_address": pool_address})(),  # tiny shim for BestPool-like
        entry_unix=entry_unix,
        max_hold_sec=max_hold_sec,
        timeframe="minute",
        aggregate=1,
        before_timestamp=before_ts,
        limit=180,
        include_empty_intervals=True,
    )
    if mc and mc.data_gz and not mc.error:
        rows = load_cached_series(db, mc)
        if rows:
            return ("minute_fetch", rows)

    return ("none", [])


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
    background_tasks.add_task(
        run_truth_job,
        channel_key=channel_key,
        strategy_key="__cache_only__",
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


@router.get("/grid", response_model=GridSimOut)
def truth_grid_simulation(
    channel_key: str = Query(..., min_length=1),
    tp_values: str = Query(default="35,40,45,50,55,60,65"),
    sl_values: str = Query(default="20,25,30,35,40,45,50"),
    start_balance_sol: float = Query(default=1.0, gt=0),
    entry_sol: float | None = Query(default=None, gt=0),
    prefer_seconds: bool = Query(default=True),
    max_hold_sec: int = Query(default=MAX_HOLD_SEC, ge=60, le=60 * 60),
):
    """
    Truth-grid simulation using cached OHLCV in truth_ohlcv_cache (seconds first, fallback minute).

    - Uses DONE calls only.
    - For each call we resolve the best pool (same as truth job).
    - Reads cached seconds series if good; otherwise minute cache; otherwise fetch minute once and cache it.

    Skips calls where outcome is AMBIGUOUS or no data.
    """

    trade_entry_sol = float(entry_sol) if entry_sol is not None else float(
        getattr(settings, "PAPER_ENTRY_SOL", 0.1)
    )

    tp_list = _parse_csv_floats(tp_values)
    sl_list = _parse_csv_floats(sl_values)
    if not tp_list or not sl_list:
        raise HTTPException(status_code=400, detail="tp_values and sl_values must contain at least one value each")

    cg = CoinGeckoOnchainClient()

    with SessionLocal() as db:  # type: Session
        ch = db.execute(select(Channel).where(Channel.key == channel_key)).scalar_one_or_none()
        if not ch:
            raise HTTPException(status_code=404, detail="Channel not found")

        calls = list(
            db.execute(
                select(Call)
                .where(Call.channel_id == ch.id)
                .where(Call.status == "DONE")
                .order_by(Call.started_at.asc(), Call.id.asc())
            ).scalars().all()
        )

        usable_calls: list[Call] = []
        for c in calls:
            # truth eval needs entry and started_at; entry can come from call.entry_price_usd
            if c.started_at is None:
                continue
            if c.entry_price_usd is None or float(c.entry_price_usd) <= 0:
                continue
            usable_calls.append(c)

        results: list[GridCellOut] = []

        for tp in tp_list:
            for sl in sl_list:
                bal = float(start_balance_sol)
                n_trades = 0
                tp_n = 0
                sl_n = 0
                time_n = 0
                sum_pnl = 0.0

                for c in usable_calls:
                    entry_unix = int(c.started_at.replace(tzinfo=timezone.utc).timestamp())
                    entry_price = float(c.entry_price_usd)

                    # resolve pool (same as truth job)
                    best_pool = cg.pick_best_pool_for_mint(c.mint, network="solana")
                    if not best_pool:
                        continue

                    source, rows = _load_truth_series_for_call(
                        db,
                        cg,
                        call=c,
                        pool_address=best_pool.pool_address,
                        dex_id=best_pool.dex_id,
                        entry_unix=entry_unix,
                        max_hold_sec=int(max_hold_sec),
                        prefer_seconds=bool(prefer_seconds),
                    )
                    if not rows:
                        continue

                    outcome, pnl_pct = _evaluate_outcome_from_ohlcv(
                        rows,
                        entry_price=entry_price,
                        tp_pct=float(tp),
                        sl_pct=float(sl),
                        entry_unix=entry_unix,
                        max_hold_sec=int(max_hold_sec),
                    )

                    # skip ambiguous (we don't know TP/SL ordering inside candle)
                    if outcome == "AMBIGUOUS":
                        continue

                    n_trades += 1
                    sum_pnl += float(pnl_pct)

                    if outcome == "TP":
                        tp_n += 1
                    elif outcome == "SL":
                        sl_n += 1
                    else:
                        time_n += 1

                    pos = min(trade_entry_sol, bal)
                    pnl_sol = pos * (float(pnl_pct) / 100.0)
                    bal += pnl_sol

                avg_pnl = (sum_pnl / n_trades) if n_trades else 0.0
                win_rate = (100.0 * tp_n / n_trades) if n_trades else 0.0

                results.append(
                    GridCellOut(
                        tp_pct=float(tp),
                        sl_pct=float(sl),
                        n_trades=n_trades,
                        tp=tp_n,
                        sl=sl_n,
                        time=time_n,
                        win_rate_tp_pct=_round2(win_rate),
                        avg_pnl_pct=_round2(avg_pnl),
                        start_balance_sol=_round2(float(start_balance_sol)),
                        end_balance_sol=_round2(float(bal)),
                    )
                )

        results.sort(key=lambda r: (r.end_balance_sol, r.win_rate_tp_pct, r.n_trades), reverse=True)

        return GridSimOut(
            channel_key=channel_key,
            start_balance_sol=_round2(float(start_balance_sol)),
            entry_sol=_round2(float(trade_entry_sol)),
            tp_values=tp_list,
            sl_values=sl_list,
            results=results,
        )
