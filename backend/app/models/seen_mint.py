# backend/app/models/seen_mint.py
from __future__ import annotations
from sqlalchemy import Integer, String, DateTime, func, UniqueConstraint, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base

class SeenMint(Base):
    __tablename__ = "seen_mints"
    __table_args__ = (UniqueConstraint("channel_id", "mint", name="uq_seen_channel_mint"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    channel_id: Mapped[int] = mapped_column(Integer, ForeignKey("channels.id", ondelete="CASCADE"), index=True)
    mint: Mapped[str] = mapped_column(String(64), index=True)
    first_seen_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now())
