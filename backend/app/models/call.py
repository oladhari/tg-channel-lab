# backend/app/models/call.py
from __future__ import annotations

from datetime import datetime
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy import (
    Integer,
    String,
    Text,
    Boolean,
    DateTime,
    ForeignKey,
    func,
    UniqueConstraint,
    Float,
    BigInteger,
)

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
    raw_message: Mapped[str | None] = mapped_column(Text, default=None)

    status: Mapped[str] = mapped_column(String(32), default="RECORDING")
    # RECORDING | DONE | IGNORED_NO_PRICE

    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    duration_sec: Mapped[int] = mapped_column(Integer, default=1500)

    # first price recorded
    entry_price_usd: Mapped[float | None] = mapped_column(Float, default=None)
    ignore_reason: Mapped[str | None] = mapped_column(String(200), default=None)

    # =========================
    # Snapshot fields (NO FILTERS)
    # Captured once near entry, from Dexscreener token endpoint.
    # =========================
    snapshot_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)

    # Pair identity
    pair_address: Mapped[str | None] = mapped_column(String(128), default=None)
    dex_id: Mapped[str | None] = mapped_column(String(64), default=None)
    pair_created_at_ms: Mapped[int | None] = mapped_column(BigInteger, default=None)

    # Market snapshot
    liquidity_usd: Mapped[float | None] = mapped_column(Float, default=None)
    fdv: Mapped[float | None] = mapped_column(Float, default=None)
    market_cap: Mapped[float | None] = mapped_column(Float, default=None)

    # Volume snapshot
    vol_m5: Mapped[float | None] = mapped_column(Float, default=None)
    vol_h1: Mapped[float | None] = mapped_column(Float, default=None)
    vol_h6: Mapped[float | None] = mapped_column(Float, default=None)
    vol_h24: Mapped[float | None] = mapped_column(Float, default=None)

    # Price change snapshot
    pc_m5: Mapped[float | None] = mapped_column(Float, default=None)
    pc_h1: Mapped[float | None] = mapped_column(Float, default=None)
    pc_h6: Mapped[float | None] = mapped_column(Float, default=None)
    pc_h24: Mapped[float | None] = mapped_column(Float, default=None)

    # Txns snapshot (buys/sells)
    buys_m5: Mapped[int | None] = mapped_column(Integer, default=None)
    sells_m5: Mapped[int | None] = mapped_column(Integer, default=None)
    buys_h1: Mapped[int | None] = mapped_column(Integer, default=None)
    sells_h1: Mapped[int | None] = mapped_column(Integer, default=None)

    # relationships
    channel = relationship("Channel", back_populates="calls")
    prices = relationship("PricePoint", back_populates="call", cascade="all, delete-orphan")
    strategy_results = relationship("StrategyResult", back_populates="call", uselist=True, cascade="all, delete-orphan")


    live_sell_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    # snapshot at time of entry: whether live was enabled for this channel when call was created

    live_sell_status: Mapped[str] = mapped_column(String(32), default="NONE")
    # NONE | SENT | FALLBACK_GMGN | ERROR

    live_sell_reason: Mapped[str | None] = mapped_column(String(16), default=None)
    # TP | SL | TIME

    live_sell_sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    live_sell_error: Mapped[str | None] = mapped_column(Text, default=None)
    
    # =========================
    # LIVE BUY (GMGN)
    # =========================
    live_buy_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    # snapshot at time of entry: whether live was enabled for this channel when call was created

    live_buy_status: Mapped[str] = mapped_column(String(32), default="NONE")
    # NONE | SENT | FALLBACK_GMGN | ERROR
    live_buy_amount_sol: Mapped[float | None] = mapped_column(Float, default=None)

    live_buy_sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), default=None)
    live_buy_error: Mapped[str | None] = mapped_column(Text, default=None)
