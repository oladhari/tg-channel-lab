# backend/app/models/price_point.py
from __future__ import annotations

from datetime import datetime
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy import BigInteger, Integer, Float, String, DateTime, ForeignKey, func

from app.db.base import Base


class PricePoint(Base):
    __tablename__ = "price_points"
    # Unique constraint on (call_id, t_sec) was dropped in migration c3d4e5f6a7b8
    # to allow multiple sub-second points during burst recording mode.

    id: Mapped[int] = mapped_column(primary_key=True)
    call_id: Mapped[int] = mapped_column(ForeignKey("calls.id", ondelete="CASCADE"), index=True)

    t_sec: Mapped[int] = mapped_column(Integer, index=True)   # seconds since call started
    t_ms: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)  # ms since call started
    price_usd: Mapped[float] = mapped_column(Float)
    source: Mapped[str | None] = mapped_column(String(20), nullable=True)  # pump_ws | http | live_mon

    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    call = relationship("Call", back_populates="prices")
