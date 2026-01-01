# backend/app/schemas/stats.py
from __future__ import annotations

from pydantic import BaseModel


class PaperStatsOut(BaseModel):
    channel_id: int
    key: str
    telegram_username: str

    strategy_key: str
    start_balance_sol: float
    end_balance_sol: float

    n_trades: int
    tp: int
    sl: int
    time: int

    win_rate_tp_pct: float
    avg_pnl_pct: float

    class Config:
        from_attributes = True
