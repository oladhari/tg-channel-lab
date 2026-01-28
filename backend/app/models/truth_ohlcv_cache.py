# backend/app/models/truth_ohlcv_cache.py
from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import BYTEA
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class TruthOhlcvCache(Base):
    """
    Cache OHLCV for a call over the truth window so we can replay many TP/SL strategies
    without re-calling CoinGecko.

    data_gz is gzip-compressed JSON string: [[ts,o,h,l,c,v], ...]
    """

    __tablename__ = "truth_ohlcv_cache"
    __table_args__ = (
        UniqueConstraint("call_id", "pool_address", "timeframe", "aggregate", name="uq_truth_cache_key"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    call_id: Mapped[int] = mapped_column(ForeignKey("calls.id", ondelete="CASCADE"), nullable=False)
    call = relationship("Call", back_populates="truth_ohlcv_cache_items")

    network: Mapped[str] = mapped_column(String(32), nullable=False, default="solana")
    dex_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    pool_address: Mapped[str] = mapped_column(String(128), nullable=False)

    timeframe: Mapped[str] = mapped_column(String(16), nullable=False)  # "second" | "minute"
    aggregate: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    entry_unix: Mapped[int] = mapped_column(BigInteger, nullable=False)
    max_hold_sec: Mapped[int] = mapped_column(Integer, nullable=False)

    start_ts: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    end_ts: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    points: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    source: Mapped[str] = mapped_column(String(64), nullable=False, default="coingecko_onchain")
    fetched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    data_gz: Mapped[bytes | None] = mapped_column(BYTEA, nullable=True)
    error: Mapped[str | None] = mapped_column(String(280), nullable=True)
