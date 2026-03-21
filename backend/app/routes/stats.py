# backend/app/routes/stats.py
from __future__ import annotations

import time as _time
import threading as _threading

from fastapi import APIRouter, Query, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.settings import settings
from app.db.session import SessionLocal
from app.models import Channel, Call, StrategyResult
from app.schemas.stats import PaperStatsOut, GridSimOut, GridCellOut, BestStatOut
from app.services.geckoterm import get_top_pool, get_ohlcv_candles, simulate_with_candles

router = APIRouter(prefix="/stats", tags=["stats"])


def _round2(x: float) -> float:
    return float(round(x, 2))


# =========================================================
# PAPER STATS (reads existing StrategyResult rows)
# =========================================================
@router.get("/paper", response_model=list[PaperStatsOut])
def paper_stats(
    strategy_key: str = Query(default="tp35_sl20"),
    start_balance_sol: float = Query(default=1.0, gt=0),
    entry_sol: float | None = Query(default=None, gt=0),
    channel_key: str | None = Query(default=None),
):
    """
    Paper stats per channel for a given strategy_key.

    IMPORTANT:
    Previously this endpoint compounded the entire balance:
      balance *= (1 + pnl_pct/100)

    Now it applies pnl_pct only to a per-trade position size (entry_sol):
      pnl_sol = position_sol * (pnl_pct/100)
      balance += pnl_sol

    Where:
      position_sol = min(entry_sol, current_balance)  # cannot trade more than you have
    """
    trade_entry_sol = float(entry_sol) if entry_sol is not None else float(
        getattr(settings, "PAPER_ENTRY_SOL", 0.1)
    )

    db: Session = SessionLocal()
    try:
        stmt = (
            select(
                Channel.id,
                Channel.key,
                Channel.telegram_username,
                StrategyResult.outcome,
                StrategyResult.pnl_pct,
                Call.started_at,
            )
            .join(Call, Call.channel_id == Channel.id)
            .join(StrategyResult, StrategyResult.call_id == Call.id)
            .where(StrategyResult.strategy_key == strategy_key)
        )

        # ✅ optional filter: stats for a single channel only
        if channel_key:
            stmt = stmt.where(Channel.key == channel_key)

        stmt = stmt.order_by(Channel.id.asc(), Call.started_at.asc(), StrategyResult.id.asc())

        rows = db.execute(stmt).all()

        per: dict[int, dict] = {}
        for channel_id, key, username, outcome, pnl_pct, started_at in rows:
            if channel_id not in per:
                per[channel_id] = {
                    "channel_id": channel_id,
                    "key": key,
                    "telegram_username": username,
                    "strategy_key": strategy_key,
                    "start_balance_sol": float(start_balance_sol),
                    "end_balance_sol": float(start_balance_sol),
                    "n_trades": 0,
                    "tp": 0,
                    "sl": 0,
                    "time": 0,
                    "sum_pnl": 0.0,
                }

            rec = per[channel_id]
            rec["n_trades"] += 1
            rec["sum_pnl"] += float(pnl_pct)

            out = (outcome or "").upper()
            if out == "TP":
                rec["tp"] += 1
            elif out == "SL":
                rec["sl"] += 1
            else:
                rec["time"] += 1

            # ✅ apply pnl on position size, not full balance
            bal = float(rec["end_balance_sol"])
            pos = min(trade_entry_sol, bal)
            pnl_sol = pos * (float(pnl_pct) / 100.0)
            rec["end_balance_sol"] = bal + pnl_sol

        out_list: list[PaperStatsOut] = []
        for rec in per.values():
            n = rec["n_trades"]
            avg_pnl = (rec["sum_pnl"] / n) if n else 0.0
            win_rate = (100.0 * rec["tp"] / n) if n else 0.0

            out_list.append(
                PaperStatsOut(
                    channel_id=rec["channel_id"],
                    key=rec["key"],
                    telegram_username=rec["telegram_username"],
                    strategy_key=rec["strategy_key"],
                    start_balance_sol=_round2(rec["start_balance_sol"]),
                    end_balance_sol=_round2(rec["end_balance_sol"]),
                    n_trades=rec["n_trades"],
                    tp=rec["tp"],
                    sl=rec["sl"],
                    time=rec["time"],
                    win_rate_tp_pct=_round2(win_rate),
                    avg_pnl_pct=_round2(avg_pnl),
                )
            )

        out_list.sort(key=lambda x: x.end_balance_sol, reverse=True)
        return out_list

    finally:
        db.close()


# =========================================================
# BEST STRATEGY PER CHANNEL  (wide grid + 5-min TTL cache)
# =========================================================

# TP: 20 → 100 step 5  (17 values)
# SL: 10 → 50 step 5   (9 values)
# Total: 153 combinations per channel
_BEST_TP = list(range(20, 105, 5))   # [20, 25, ..., 100]
_BEST_SL = list(range(10, 55, 5))    # [10, 15, ..., 50]

_BEST_CACHE_TTL = 300  # seconds
_best_cache: dict = {"data": None, "params": None, "ts": 0.0}
_best_lock = _threading.Lock()
_best_worker: _threading.Thread | None = None


def _run_best_stats_bg(start_balance_sol: float, trade_entry_sol: float, cache_key: tuple) -> None:
    """Background thread: runs the full grid and updates the cache."""
    global _best_cache, _best_worker
    db: Session = SessionLocal()
    now = _time.time()
    try:
        channels = list(db.execute(select(Channel)).scalars().all())
        out_list: list[BestStatOut] = []

        for ch in channels:
            stmt = (
                select(Call)
                .where(Call.channel_id == ch.id)
                .where(Call.status == "DONE")
                .options(selectinload(Call.prices))
                .order_by(Call.started_at.asc())
            )
            calls = list(db.execute(stmt).scalars().all())
            usable = [c for c in calls if c.entry_price_usd is not None or (c.prices and len(c.prices) > 0)]
            if not usable:
                continue

            best: dict | None = None
            for tp in _BEST_TP:
                for sl in _BEST_SL:
                    bal = float(start_balance_sol)
                    n_trades = tp_n = sl_n = time_n = 0
                    sum_pnl = 0.0
                    for c in usable:
                        outcome, pnl_pct = _simulate_one_call(c, float(tp), float(sl))
                        n_trades += 1
                        sum_pnl += pnl_pct
                        out = outcome.upper()
                        if out == "TP":
                            tp_n += 1
                        elif out == "SL":
                            sl_n += 1
                        else:
                            time_n += 1
                        pos = min(trade_entry_sol, bal)
                        bal += pos * (pnl_pct / 100.0)
                    if best is None or bal > best["end_balance_sol"]:
                        avg_pnl = (sum_pnl / n_trades) if n_trades else 0.0
                        win_rate = (100.0 * tp_n / n_trades) if n_trades else 0.0
                        best = {
                            "best_tp_pct": float(tp), "best_sl_pct": float(sl),
                            "n_trades": n_trades, "tp": tp_n, "sl": sl_n, "time": time_n,
                            "win_rate_tp_pct": _round2(win_rate), "avg_pnl_pct": _round2(avg_pnl),
                            "start_balance_sol": _round2(float(start_balance_sol)),
                            "end_balance_sol": _round2(float(bal)),
                        }

            if best:
                out_list.append(BestStatOut(
                    channel_id=ch.id, key=ch.key, telegram_username=ch.telegram_username,
                    computed_at=now, **best,
                ))

        out_list.sort(key=lambda x: x.end_balance_sol, reverse=True)
        with _best_lock:
            _best_cache["data"] = out_list
            _best_cache["ts"] = now
            _best_cache["params"] = cache_key
    except Exception as _exc:
        print(f"[STATS][best_stats_bg] ERROR: {_exc}", flush=True)
    finally:
        db.close()
        with _best_lock:
            _best_worker = None


@router.get("/best", response_model=list[BestStatOut])
def best_stats(
    start_balance_sol: float = Query(default=1.0, gt=0),
    entry_sol: float | None = Query(default=None, gt=0),
):
    """
    For every channel, run a full TP/SL grid (153 combos) over DONE calls
    and return the single best-performing strategy per channel.

    Results are cached in memory for 5 minutes.
    On cache miss the computation runs in a background thread — the endpoint
    returns immediately (stale data or empty list) so the dashboard never hangs.
    """
    global _best_worker
    trade_entry_sol = float(entry_sol) if entry_sol is not None else float(
        getattr(settings, "PAPER_ENTRY_SOL", 0.1)
    )
    cache_key = (round(start_balance_sol, 4), round(trade_entry_sol, 4))
    now = _time.time()

    with _best_lock:
        if (
            _best_cache["data"] is not None
            and _best_cache["params"] == cache_key
            and (now - _best_cache["ts"]) < _BEST_CACHE_TTL
        ):
            return _best_cache["data"]

        # Cache is cold — kick off background computation if not already running
        if _best_worker is None or not _best_worker.is_alive():
            _best_worker = _threading.Thread(
                target=_run_best_stats_bg,
                args=(start_balance_sol, trade_entry_sol, cache_key),
                daemon=True,
            )
            _best_worker.start()

        # Return stale data if available, otherwise empty list (computing in bg)
        return _best_cache["data"] or []


# =========================================================
# GRID SIMULATION (recomputes from price_points)
# =========================================================
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
    # de-dupe + stable sort
    return sorted(set(vals))


def _simulate_one_call(call: Call, tp_pct: float, sl_pct: float) -> tuple[str, float]:
    """
    Returns (outcome, pnl_pct) for this call, based on its price_points.
    outcome: TP | SL | TIME
    pnl_pct: +tp_pct for TP, -sl_pct for SL, else TIME uses last_price vs entry
    """
    entry = call.entry_price_usd
    points = list(call.prices or [])
    points.sort(key=lambda p: p.t_sec)

    # If entry is missing, fall back to first price point
    if entry is None:
        if not points:
            return ("TIME", 0.0)
        entry = float(points[0].price_usd)

    if entry <= 0:
        return ("TIME", 0.0)

    tp_target = entry * (1.0 + tp_pct / 100.0)
    sl_target = entry * (1.0 - sl_pct / 100.0)

    last_price = entry

    for p in points:
        price = float(p.price_usd)
        last_price = price

        if price >= tp_target:
            return ("TP", float(tp_pct))
        if price <= sl_target:
            return ("SL", -float(sl_pct))

    # TIME: mark-to-last
    pnl_pct = ((last_price / entry) - 1.0) * 100.0
    return ("TIME", float(pnl_pct))


@router.get("/grid", response_model=GridSimOut)
def grid_simulation(
    channel_key: str = Query(..., min_length=1),
    tp_values: str = Query(default="35,40,45,50,55,60,65"),
    sl_values: str = Query(default="20,25,30,35,40,45,50"),
    start_balance_sol: float = Query(default=1.0, gt=0),
    entry_sol: float | None = Query(default=None, gt=0),
):
    """
    Grid simulation per channel, using raw price_points for each call.
    This does NOT rely on StrategyResult table; it recomputes outcomes for each TP/SL combo.

    IMPORTANT:
    We simulate ONLY DONE calls (same as your "only done of course" rule).
    """
    trade_entry_sol = float(entry_sol) if entry_sol is not None else float(
        getattr(settings, "PAPER_ENTRY_SOL", 0.1)
    )

    tp_list = _parse_csv_floats(tp_values)
    sl_list = _parse_csv_floats(sl_values)

    if not tp_list or not sl_list:
        raise HTTPException(status_code=400, detail="tp_values and sl_values must contain at least one value each")

    db: Session = SessionLocal()
    try:
        ch = db.execute(select(Channel).where(Channel.key == channel_key)).scalar_one_or_none()
        if not ch:
            raise HTTPException(status_code=404, detail="Channel not found")

        # ✅ ONLY DONE calls (skip RECORDING + IGNORED_NO_PRICE)
        stmt = (
            select(Call)
            .where(Call.channel_id == ch.id)
            .where(Call.status == "DONE")
            .options(selectinload(Call.prices))
            .order_by(Call.started_at.asc(), Call.id.asc())
        )
        calls = list(db.execute(stmt).scalars().all())

        # keep only calls that have some usable data (entry OR at least 1 point)
        usable: list[Call] = []
        for c in calls:
            if c.entry_price_usd is not None:
                usable.append(c)
                continue
            if c.prices and len(c.prices) > 0:
                usable.append(c)

        results: list[GridCellOut] = []

        for tp in tp_list:
            for sl in sl_list:
                bal = float(start_balance_sol)
                n_trades = 0
                tp_n = 0
                sl_n = 0
                time_n = 0
                sum_pnl = 0.0

                for c in usable:
                    outcome, pnl_pct = _simulate_one_call(c, tp, sl)

                    n_trades += 1
                    sum_pnl += float(pnl_pct)

                    out = (outcome or "").upper()
                    if out == "TP":
                        tp_n += 1
                    elif out == "SL":
                        sl_n += 1
                    else:
                        time_n += 1

                    # same paper rule as /paper: pnl applies only to position size
                    pos = min(trade_entry_sol, bal)
                    pnl_sol = pos * (float(pnl_pct) / 100.0)
                    bal = bal + pnl_sol

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

        # sort best first
        results.sort(key=lambda r: (r.end_balance_sol, r.win_rate_tp_pct, r.n_trades), reverse=True)

        return GridSimOut(
            channel_key=channel_key,
            start_balance_sol=_round2(float(start_balance_sol)),
            entry_sol=_round2(float(trade_entry_sol)),
            tp_values=tp_list,
            sl_values=sl_list,
            results=results,
        )

    finally:
        db.close()


# =========================================================
# ACCURATE GRID SIMULATION (uses GeckoTerminal OHLCV candles)
# =========================================================
@router.get("/accurate-grid", response_model=GridSimOut)
def accurate_grid_simulation(
    channel_key: str = Query(..., min_length=1),
    tp_values: str = Query(default="35,40,45,50,55,60,65"),
    sl_values: str = Query(default="20,25,30,35,40,45,50"),
    start_balance_sol: float = Query(default=1.0, gt=0),
    entry_sol: float | None = Query(default=None, gt=0),
):
    """
    Grid simulation using 1-minute OHLCV candles from GeckoTerminal.
    Uses candle high/low for accurate TP/SL detection instead of our
    2-5s recorded price points.
    Falls back to recorded points if OHLCV is unavailable for a call.
    """
    trade_entry_sol = float(entry_sol) if entry_sol is not None else float(
        getattr(settings, "PAPER_ENTRY_SOL", 0.1)
    )

    tp_list = _parse_csv_floats(tp_values)
    sl_list = _parse_csv_floats(sl_values)

    if not tp_list or not sl_list:
        raise HTTPException(status_code=400, detail="tp_values and sl_values must contain at least one value each")

    db: Session = SessionLocal()
    try:
        ch = db.execute(select(Channel).where(Channel.key == channel_key)).scalar_one_or_none()
        if not ch:
            raise HTTPException(status_code=404, detail="Channel not found")

        stmt = (
            select(Call)
            .where(Call.channel_id == ch.id)
            .where(Call.status == "DONE")
            .where(Call.entry_price_usd.isnot(None))
            .options(selectinload(Call.prices))
            .order_by(Call.started_at.asc(), Call.id.asc())
        )
        calls = list(db.execute(stmt).scalars().all())

        # Pre-fetch pool addresses and OHLCV candles per mint (cache by mint)
        pool_cache: dict[str, str | None] = {}
        candle_cache: dict[str, list] = {}

        for call in calls:
            mint = call.mint
            if mint in candle_cache:
                continue

            pool = pool_cache.get(mint)
            if pool is None and mint not in pool_cache:
                pool = get_top_pool(mint)
                pool_cache[mint] = pool

            if not pool:
                candle_cache[mint] = []
                continue

            start_ts = int(call.started_at.timestamp())
            end_ts = start_ts + call.duration_sec + 120  # buffer
            candles = get_ohlcv_candles(pool, before_timestamp=end_ts, limit=40)
            candle_cache[mint] = candles

        results: list[GridCellOut] = []

        for tp in tp_list:
            for sl in sl_list:
                bal = float(start_balance_sol)
                n_trades = tp_n = sl_n = time_n = 0
                sum_pnl = 0.0

                for call in calls:
                    entry = float(call.entry_price_usd)
                    start_ts = int(call.started_at.timestamp())
                    end_ts = start_ts + call.duration_sec
                    candles = candle_cache.get(call.mint, [])

                    if candles:
                        outcome, pnl_pct = simulate_with_candles(
                            candles, entry, tp, sl, start_ts, end_ts
                        )
                    else:
                        # Fallback to recorded price points
                        outcome, pnl_pct = _simulate_one_call(call, tp, sl)

                    n_trades += 1
                    sum_pnl += pnl_pct
                    out = outcome.upper()
                    if out == "TP":
                        tp_n += 1
                    elif out == "SL":
                        sl_n += 1
                    else:
                        time_n += 1

                    pos = min(trade_entry_sol, bal)
                    bal += pos * (pnl_pct / 100.0)

                avg_pnl = (sum_pnl / n_trades) if n_trades else 0.0
                win_rate = (100.0 * tp_n / n_trades) if n_trades else 0.0

                results.append(GridCellOut(
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
                ))

        results.sort(key=lambda r: (r.end_balance_sol, r.win_rate_tp_pct, r.n_trades), reverse=True)

        return GridSimOut(
            channel_key=channel_key,
            start_balance_sol=_round2(float(start_balance_sol)),
            entry_sol=_round2(float(trade_entry_sol)),
            tp_values=tp_list,
            sl_values=sl_list,
            results=results,
        )

    finally:
        db.close()
