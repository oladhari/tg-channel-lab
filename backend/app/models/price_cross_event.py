# backend/app/models/price_cross_event.py
"""
Records the FIRST time a token's price crosses a TP or SL threshold level
during a call's recording window.

One row per (call_id, event_type, level_pct) — captured with millisecond
precision so downstream simulation can determine which threshold was crossed
first without relying on 2-5 second polling snapshots.

event_type: "TP_CROSS" | "SL_CROSS"
level_pct:  the threshold, e.g. 35.0 (TP +35%) or 20.0 (SL -20%)
t_ms:       milliseconds since call.started_at
"""
from __future__ import annotations

from datetime import datetime
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import BigInteger, Float, String, DateTime, ForeignKey

from app.db.base import Base


class PriceCrossEvent(Base):
    __tablename__ = "price_cross_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    call_id: Mapped[int] = mapped_column(
        ForeignKey("calls.id", ondelete="CASCADE"), index=True, nullable=False
    )

    # Milliseconds since call.started_at — primary ordering key
    t_ms: Mapped[int] = mapped_column(BigInteger, nullable=False)

    # Absolute UTC wall-clock time for cross-referencing
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    price_usd: Mapped[float] = mapped_column(Float, nullable=False)

    # "TP_CROSS" or "SL_CROSS"
    event_type: Mapped[str] = mapped_column(String(20), nullable=False)

    # The threshold percentage: 35.0 means +35% TP or -35% SL
    level_pct: Mapped[float] = mapped_column(Float, nullable=False)

    # Price source that observed this crossing
    source: Mapped[str] = mapped_column(String(20), nullable=False)
