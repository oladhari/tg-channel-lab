from __future__ import annotations

from datetime import datetime
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy import Integer, String, DateTime, ForeignKey, func, UniqueConstraint

from app.db.base import Base


class Call(Base):
    __tablename__ = "calls"
    __table_args__ = (
        # per-channel dedupe: do not create another call for same mint in same channel
        UniqueConstraint("channel_id", "mint", name="uq_calls_channel_mint"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)

    channel_id: Mapped[int] = mapped_column(ForeignKey("channels.id", ondelete="CASCADE"), index=True)

    mint: Mapped[str] = mapped_column(String(64), index=True)
    symbol: Mapped[str] = mapped_column(String(32), default="")

    status: Mapped[str] = mapped_column(String(32), default="RECORDING")  
    # RECORDING | DONE | IGNORED_NO_PRICE

    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    duration_sec: Mapped[int] = mapped_column(Integer, default=1500)

    entry_price_usd: Mapped[float | None] = mapped_column(default=None)  # first price recorded
    ignore_reason: Mapped[str | None] = mapped_column(String(200), default=None)

    channel = relationship("Channel", back_populates="calls")
    prices = relationship("PricePoint", back_populates="call", cascade="all, delete-orphan")
    display_result = relationship("StrategyResult", back_populates="call", uselist=False, cascade="all, delete-orphan")
