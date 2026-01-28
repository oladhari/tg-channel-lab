# backend/app/services/truth_cache.py
from __future__ import annotations

import gzip
import json
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import TruthOhlcvCache, Call
from app.services.coingecko_onchain import CoinGeckoOnchainClient, BestPool


@dataclass(frozen=True)
class CachedSeries:
    pool: BestPool
    timeframe: str
    aggregate: int
    rows: list[list[float]]


def encode_rows_gz(rows: list[list[float]]) -> bytes:
    payload = json.dumps(rows, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return gzip.compress(payload, compresslevel=6)


def decode_rows_gz(data_gz: bytes) -> list[list[float]]:
    raw = gzip.decompress(data_gz).decode("utf-8")
    return json.loads(raw)


def _minmax_ts(rows: list[list[float]]) -> tuple[int | None, int | None]:
    ts = []
    for r in rows:
        if isinstance(r, list) and len(r) >= 1:
            try:
                ts.append(int(r[0]))
            except Exception:
                pass
    if not ts:
        return None, None
    return min(ts), max(ts)


def get_cache(
    db: Session,
    *,
    call_id: int,
    pool_address: str,
    timeframe: str,
    aggregate: int,
) -> TruthOhlcvCache | None:
    q = (
        select(TruthOhlcvCache)
        .where(TruthOhlcvCache.call_id == call_id)
        .where(TruthOhlcvCache.pool_address == pool_address)
        .where(TruthOhlcvCache.timeframe == timeframe)
        .where(TruthOhlcvCache.aggregate == aggregate)
    )
    return db.execute(q).scalar_one_or_none()


def upsert_cache(
    db: Session,
    *,
    call: Call,
    pool: BestPool,
    timeframe: str,
    aggregate: int,
    entry_unix: int,
    max_hold_sec: int,
    rows: list[list[float]] | None,
    error: str | None,
) -> TruthOhlcvCache:
    existing = get_cache(
        db,
        call_id=call.id,
        pool_address=pool.pool_address,
        timeframe=timeframe,
        aggregate=aggregate,
    )

    if existing is None:
        existing = TruthOhlcvCache(
            call_id=call.id,
            network="solana",
            dex_id=pool.dex_id,
            pool_address=pool.pool_address,
            timeframe=timeframe,
            aggregate=aggregate,
            entry_unix=entry_unix,
            max_hold_sec=max_hold_sec,
        )
        db.add(existing)

    existing.dex_id = pool.dex_id
    existing.entry_unix = entry_unix
    existing.max_hold_sec = max_hold_sec
    existing.source = "coingecko_onchain"
    existing.fetched_at = datetime.now(timezone.utc)

    if rows:
        data_gz = encode_rows_gz(rows)
        start_ts, end_ts = _minmax_ts(rows)
        existing.data_gz = data_gz
        existing.points = len(rows)
        existing.start_ts = start_ts
        existing.end_ts = end_ts
        existing.error = None
    else:
        existing.data_gz = None
        existing.points = 0
        existing.start_ts = None
        existing.end_ts = None
        existing.error = (error or "unknown_error")[:280]

    db.commit()
    db.refresh(existing)
    return existing


def fetch_and_store(
    db: Session,
    *,
    cg: CoinGeckoOnchainClient,
    call: Call,
    pool: BestPool,
    entry_unix: int,
    max_hold_sec: int,
    timeframe: str,
    aggregate: int,
    before_timestamp: int,
    limit: int,
    include_empty_intervals: bool,
) -> TruthOhlcvCache:
    try:
        rows = cg.fetch_ohlcv(
            pool.pool_address,
            timeframe,
            network="solana",
            aggregate=aggregate,
            before_timestamp=before_timestamp,
            limit=limit,
            currency="usd",
            token="base",
            include_empty_intervals=include_empty_intervals,
        )
        return upsert_cache(
            db,
            call=call,
            pool=pool,
            timeframe=timeframe,
            aggregate=aggregate,
            entry_unix=entry_unix,
            max_hold_sec=max_hold_sec,
            rows=rows,
            error=None,
        )
    except Exception as e:
        return upsert_cache(
            db,
            call=call,
            pool=call and pool,
            timeframe=timeframe,
            aggregate=aggregate,
            entry_unix=entry_unix,
            max_hold_sec=max_hold_sec,
            rows=None,
            error=str(e),
        )


def load_cached_series(db: Session, cache: TruthOhlcvCache) -> list[list[float]]:
    if not cache.data_gz:
        return []
    return decode_rows_gz(cache.data_gz)
