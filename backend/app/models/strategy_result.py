# backend/app/models/strategy_result.py
from __future__ import annotations

from datetime import datetime
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy import Float, Integer, String, DateTime, ForeignKey, func, UniqueConstraint

from app.db.base import Base


class StrategyResult(Base):
    __tablename__ = "strategy_results"
    __table_args__ = (
        UniqueConstraint("call_id", "strategy_key", name="uq_strategy_results_call_strategy"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    call_id: Mapped[int] = mapped_column(ForeignKey("calls.id", ondelete="CASCADE"), index=True)

    strategy_key: Mapped[str] = mapped_column(String(64))  # "tp35_sl20"
    tp_pct: Mapped[float] = mapped_column(Float)
    sl_pct: Mapped[float] = mapped_column(Float)

    entry_price_usd: Mapped[float] = mapped_column(Float)
    exit_price_usd: Mapped[float] = mapped_column(Float)
    exit_t_sec: Mapped[int] = mapped_column(Integer)  # when TP/SL hit, or duration end
    outcome: Mapped[str] = mapped_column(String(16))  # TP|SL|TIME

    pnl_pct: Mapped[float] = mapped_column(Float)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    call = relationship("Call", back_populates="display_result")
