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


class GridCellOut(BaseModel):
    tp_pct: float
    sl_pct: float

    n_trades: int
    tp: int
    sl: int
    time: int

    win_rate_tp_pct: float
    avg_pnl_pct: float

    start_balance_sol: float
    end_balance_sol: float


class GridSimOut(BaseModel):
    channel_key: str
    start_balance_sol: float
    entry_sol: float

    tp_values: list[float]
    sl_values: list[float]

    results: list[GridCellOut]


class BestStatOut(BaseModel):
    channel_id: int
    key: str
    telegram_username: str

    best_tp_pct: float
    best_sl_pct: float

    n_trades: int
    tp: int
    sl: int
    time: int

    win_rate_tp_pct: float
    avg_pnl_pct: float

    start_balance_sol: float
    end_balance_sol: float

    computed_at: float  # unix timestamp when cache was last built
