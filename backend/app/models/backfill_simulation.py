# backend/app/models/backfill_simulation.py
from __future__ import annotations

from datetime import datetime
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import Integer, String, Float, DateTime, Text, UniqueConstraint, func

from app.db.base import Base


class BackfillSimulation(Base):
    __tablename__ = "backfill_simulations"
    __table_args__ = (
        # Never process the same token from the same channel at the same detection time twice
        UniqueConstraint("channel_id", "mint", "detected_at", name="uq_backfill_channel_mint_detected"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)

    channel_id: Mapped[int] = mapped_column(Integer, index=True)
    channel_username: Mapped[str] = mapped_column(String(120))

    mint: Mapped[str] = mapped_column(String(64), index=True)

    # When the Telegram message was sent (detection time)
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)

    # When this backfill row was created
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # Entry: first valid price AFTER detection
    entry_price_usd: Mapped[float | None] = mapped_column(Float, default=None)
    # How many seconds after detection the entry price was found
    entry_delay_sec: Mapped[int | None] = mapped_column(Integer, default=None)

    # Exit
    exit_price_usd: Mapped[float | None] = mapped_column(Float, default=None)
    exit_t_sec: Mapped[int | None] = mapped_column(Integer, default=None)

    # TP / SL used for simulation
    tp_pct: Mapped[float] = mapped_column(Float, default=35.0)
    sl_pct: Mapped[float] = mapped_column(Float, default=20.0)

    # TP | SL | TIME | NO_DATA | NO_ENTRY
    result: Mapped[str] = mapped_column(String(16), default="NO_DATA")

    pnl_pct: Mapped[float | None] = mapped_column(Float, default=None)
    max_profit_pct: Mapped[float | None] = mapped_column(Float, default=None)
    max_drawdown_pct: Mapped[float | None] = mapped_column(Float, default=None)

    raw_message: Mapped[str | None] = mapped_column(Text, default=None)
    error: Mapped[str | None] = mapped_column(Text, default=None)
