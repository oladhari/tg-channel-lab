from __future__ import annotations

from datetime import datetime
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy import Integer, Float, DateTime, ForeignKey, func, UniqueConstraint

from app.db.base import Base


class PricePoint(Base):
    __tablename__ = "price_points"
    __table_args__ = (
        # ensure only one point per (call_id, t_sec)
        UniqueConstraint("call_id", "t_sec", name="uq_price_points_call_tsec"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    call_id: Mapped[int] = mapped_column(ForeignKey("calls.id", ondelete="CASCADE"), index=True)

    t_sec: Mapped[int] = mapped_column(Integer, index=True)  # seconds since started
    price_usd: Mapped[float] = mapped_column(Float)

    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    call = relationship("Call", back_populates="prices")
