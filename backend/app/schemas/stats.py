# backend/app/schemas/stats.py
from __future__ import annotations

from datetime import datetime
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
    score: float | None = None   # avg_pnl in pnl mode; avg_pnl * win_rate in risk_adjusted mode

    start_balance_sol: float
    end_balance_sol: float


class GridSimOut(BaseModel):
    channel_key: str
    start_balance_sol: float
    entry_sol: float

    tp_values: list[float]
    sl_values: list[float]

    results: list[GridCellOut]


class ExplorerCallOut(BaseModel):
    call_id: int
    mint: str
    symbol: str | None
    started_at: datetime
    entry_price_usd: float | None
    outcome: str          # TP | SL | TIME
    pnl_pct: float
    exit_t_sec: int | None
    exit_price_usd: float | None


class StrategyExplorerOut(BaseModel):
    channel_key: str
    n_calls: int
    best_tp_pct: float | None
    best_sl_pct: float | None
    all_results: list["GridCellOut"]   # all combos, sorted by avg_pnl DESC


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
