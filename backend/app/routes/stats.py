# backend/app/routes/stats.py
from __future__ import annotations

from fastapi import APIRouter, Query, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.settings import settings
from app.db.session import SessionLocal
from app.models import Channel, Call, StrategyResult, PricePoint
from app.schemas.stats import PaperStatsOut, GridSimOut, GridCellOut

router = APIRouter(prefix="/stats", tags=["stats"])

def _round2(x: float) -> float:
    return float(round(x, 2))


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
    trade_entry_sol = float(entry_sol) if entry_sol is not None else float(getattr(settings, "PAPER_ENTRY_SOL", 0.1))

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

        out_list.sort(key=lambda x: (x.n_trades, x.end_balance_sol), reverse=True)
        return out_list

    finally:
        db.close()







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
    vals = sorted(set(vals))
    return vals


def _simulate_one_call(call: Call, tp_pct: float, sl_pct: float) -> tuple[str, float]:
    """
    Returns (outcome, pnl_pct) for this call, based on its price_points.
    outcome: TP | SL | TIME
    pnl_pct: +tp_pct for TP, -sl_pct for SL, else TIME uses last_price vs entry
    """
    # Determine entry
    entry = call.entry_price_usd
    points = list(call.prices or [])
    points.sort(key=lambda p: p.t_sec)

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
    """
    trade_entry_sol = float(entry_sol) if entry_sol is not None else float(getattr(settings, "PAPER_ENTRY_SOL", 0.1))
    tp_list = _parse_csv_floats(tp_values)
    sl_list = _parse_csv_floats(sl_values)

    if not tp_list or not sl_list:
        raise HTTPException(status_code=400, detail="tp_values and sl_values must contain at least one value each")

    db: Session = SessionLocal()
    try:
        ch = db.execute(select(Channel).where(Channel.key == channel_key)).scalar_one_or_none()
        if not ch:
            raise HTTPException(status_code=404, detail="Channel not found")

        # Load calls + their price points in one go
        stmt = (
            select(Call)
            .where(Call.channel_id == ch.id)
            .where(Call.status != "IGNORED_NO_PRICE")
            .options(selectinload(Call.prices))
            .order_by(Call.started_at.asc(), Call.id.asc())
        )
        calls = list(db.execute(stmt).scalars().all())

        # keep only calls that have some usable data
        usable: list[Call] = []
        for c in calls:
            if c.entry_price_usd is not None:
                usable.append(c)
                continue
            if c.prices and len(c.prices) > 0:
                usable.append(c)

        # Compute for each (tp,sl)
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
