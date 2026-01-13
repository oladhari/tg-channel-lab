# backend/app/models/channel.py
from __future__ import annotations

from datetime import datetime
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy import String, Boolean, DateTime, func, Float

from app.db.base import Base


class Channel(Base):
    __tablename__ = "channels"

    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(String(50), unique=True, index=True)  # e.g. "matt"
    telegram_username: Mapped[str] = mapped_column(String(120), unique=True, index=True)  # e.g. "mattprintalphacalls"

    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    live_enabled: Mapped[bool] = mapped_column(Boolean, default=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    # ✅ NEW: default small amount for safe testing
    live_buy_amount_sol: Mapped[float] = mapped_column(Float, default=0.005)
    calls = relationship("Call", back_populates="channel", cascade="all, delete-orphan")
