from __future__ import annotations

from fastapi import APIRouter, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.models import Channel, Call, StrategyResult
from app.schemas.stats import PaperStatsOut

router = APIRouter(prefix="/stats", tags=["stats"])


def _round2(x: float) -> float:
    return float(round(x, 2))


@router.get("/paper", response_model=list[PaperStatsOut])
def paper_stats(
    strategy_key: str = Query(default="tp35_sl20"),
    start_balance_sol: float = Query(default=1.0, gt=0),
):
    """
    Paper stats per channel for a given strategy_key.
    Compounding rule:
      balance *= (1 + pnl_pct/100) per CLOSED trade (one StrategyResult row).
    """
    db: Session = SessionLocal()
    try:
        # Pull all results with channel info in one query, ordered by time for compounding
        rows = db.execute(
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
            .order_by(Channel.id.asc(), Call.started_at.asc(), StrategyResult.id.asc())
        ).all()

        # Group per channel
        per = {}
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

            # compound
            rec["end_balance_sol"] *= (1.0 + float(pnl_pct) / 100.0)

        # Build response
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

        # Sort: most trades first, then best balance
        out_list.sort(key=lambda x: (x.n_trades, x.end_balance_sol), reverse=True)
        return out_list

    finally:
        db.close()
