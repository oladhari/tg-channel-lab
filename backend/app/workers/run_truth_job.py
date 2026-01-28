# backend/app/workers/run_truth_job.py
from __future__ import annotations

import argparse
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.models import Call, StrategyResult, Channel, TruthOhlcvCache
from app.services.coingecko_onchain import CoinGeckoOnchainClient
from app.services.truth_cache import get_cache, fetch_and_store, load_cached_series

# 🔒 STRATEGY RULE (truth check holding window)
MAX_HOLD_SEC = 25 * 60  # 25 minutes

# CoinGecko OHLCV limits
SECONDS_LIMIT = 1000
SECONDS_AGG = 1

# Special strategy key that means: ONLY warm cache, do not touch StrategyResult
CACHE_ONLY_KEY = "__cache_only__"


@dataclass(frozen=True)
class TruthEval:
    outcome: str  # TP | SL | AMBIGUOUS | TIME_EXIT | ERROR
    exit_price: float
    exit_t_sec: int


def _to_unix(dt: datetime) -> int:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return int(dt.timestamp())


def _sorted_rows(ohlcv_list: Iterable[list[float]]) -> list[list[float]]:
    rows = [r for r in ohlcv_list if isinstance(r, list) and len(r) >= 6]
    rows.sort(key=lambda r: int(r[0]))
    return rows


def _pick_close_at_or_before(rows_sorted: list[list[float]], target_ts: int) -> float | None:
    close_px: float | None = None
    for r in rows_sorted:
        ts = int(r[0])
        if ts <= target_ts:
            close_px = float(r[4])
        else:
            break
    return close_px


def _evaluate_from_ohlcv(
    ohlcv_list: list[list[float]],
    *,
    tp_price: float,
    sl_price: float,
    entry_unix: int,
    max_hold_sec: int,
) -> TruthEval:
    rows = _sorted_rows(ohlcv_list)
    target_ts = entry_unix + max_hold_sec

    for r in rows:
        ts, _o, h, l, c, _v = r
        ts = int(ts)

        if ts < entry_unix:
            continue
        if ts > target_ts:
            break

        high = float(h)
        low = float(l)
        exit_t_sec = ts - entry_unix

        hit_tp = high >= tp_price
        hit_sl = low <= sl_price

        if hit_tp and hit_sl:
            return TruthEval("AMBIGUOUS", float(c), exit_t_sec)
        if hit_tp:
            return TruthEval("TP", float(tp_price), exit_t_sec)
        if hit_sl:
            return TruthEval("SL", float(sl_price), exit_t_sec)

    close_px = _pick_close_at_or_before(rows, target_ts)
    if close_px is None:
        return TruthEval("ERROR", 0.0, 0)

    return TruthEval("TIME_EXIT", float(close_px), max_hold_sec)


def _ensure_seconds_cache(
    db: Session,
    *,
    cg: CoinGeckoOnchainClient,
    call: Call,
    pool_address: str,
    dex_id: str,
    entry_unix: int,
    max_hold_sec: int,
) -> TruthOhlcvCache | None:
    """
    Ensure we have a cached seconds series for [entry, entry+max_hold_sec].

    Because CoinGecko returns up to 1000 points, and max_hold is 1500s,
    we do TWO requests:
      - first 0..999 seconds
      - then 1000..1500 seconds
    and store as ONE combined cache row.
    """
    from app.services.coingecko_onchain import BestPool

    pool = BestPool(dex_id=dex_id, pool_address=pool_address)

    existing = get_cache(
        db,
        call_id=call.id,
        pool_address=pool_address,
        timeframe="second",
        aggregate=SECONDS_AGG,
    )
    if existing and existing.data_gz and not existing.error and existing.points >= 500:  # cheap sanity
        return existing

    target_ts = entry_unix + max_hold_sec

    # chunk1: first <=1000 seconds
    chunk1_len = min(SECONDS_LIMIT, max_hold_sec)
    chunk1_before = entry_unix + chunk1_len + 1  # include last second

    c1 = fetch_and_store(
        db,
        cg=cg,
        call=call,
        pool=pool,
        entry_unix=entry_unix,
        max_hold_sec=max_hold_sec,
        timeframe="second",
        aggregate=SECONDS_AGG,
        before_timestamp=chunk1_before,
        limit=min(1000, chunk1_len + 1),  # <=1000
        include_empty_intervals=True,
    )
    if c1.error:
        return c1

    rows = load_cached_series(db, c1)

    # chunk2: remaining (if any)
    if max_hold_sec > SECONDS_LIMIT:
        remaining = max_hold_sec - SECONDS_LIMIT
        chunk2_len = min(SECONDS_LIMIT, remaining)

        chunk2_before = target_ts + 1
        rows2 = (
            cg.fetch_ohlcv(
                pool_address,
                "second",
                network="solana",
                aggregate=SECONDS_AGG,
                before_timestamp=chunk2_before,
                limit=min(1000, chunk2_len + 1),  # <=1000
                currency="usd",
                token="base",
                include_empty_intervals=True,
            )
            or []
        )
        rows.extend(rows2)

        # merge into ONE final cache row (overwrite c1)
        from app.services.truth_cache import upsert_cache

        c_final = upsert_cache(
            db,
            call=call,
            pool=pool,
            timeframe="second",
            aggregate=SECONDS_AGG,
            entry_unix=entry_unix,
            max_hold_sec=max_hold_sec,
            rows=rows,
            error=None,
        )
        return c_final

    return c1


def _ensure_minute_cache(
    db: Session,
    *,
    cg: CoinGeckoOnchainClient,
    call: Call,
    pool_address: str,
    dex_id: str,
    entry_unix: int,
    max_hold_sec: int,
) -> TruthOhlcvCache | None:
    """
    Ensure we have a cached minute series as fallback.
    """
    from app.services.coingecko_onchain import BestPool

    pool = BestPool(dex_id=dex_id, pool_address=pool_address)

    minute_cache = get_cache(
        db,
        call_id=call.id,
        pool_address=pool_address,
        timeframe="minute",
        aggregate=1,
    )
    if minute_cache and minute_cache.data_gz and not minute_cache.error and minute_cache.points >= 5:
        return minute_cache

    before_ts = entry_unix + max_hold_sec + 120
    mc = fetch_and_store(
        db,
        cg=cg,
        call=call,
        pool=pool,
        entry_unix=entry_unix,
        max_hold_sec=max_hold_sec,
        timeframe="minute",
        aggregate=1,
        before_timestamp=before_ts,
        limit=180,  # enough for 25 min
        include_empty_intervals=True,
    )
    return mc


def run_truth_job(
    *,
    strategy_key: str = "tp35_sl20",
    channel_key: str | None = None,
    limit: int = 200,
    sleep_s: float = 0.25,
    prefer_seconds: bool = True,
    max_hold_sec: int = MAX_HOLD_SEC,
):
    """
    Two modes:

    1) Normal mode (default):
       - reads StrategyResult rows for strategy_key where truth_checked_at IS NULL
       - fills truth_* fields based on cached/fetched OHLCV

    2) Cache-only mode (strategy_key="__cache_only__"):
       - iterates DONE calls (optionally filtered by channel)
       - ONLY warms truth_ohlcv_cache (seconds preferred, minute fallback)
       - does NOT read or write StrategyResult
    """
    cg = CoinGeckoOnchainClient()
    t0 = time.time()

    with SessionLocal() as db:  # type: Session

        # =========================================================
        # MODE 2: CACHE ONLY
        # =========================================================
        if strategy_key == CACHE_ONLY_KEY:
            cq = select(Call).where(Call.status == "DONE").order_by(Call.id.desc()).limit(limit)
            if channel_key:
                cq = cq.join(Channel, Channel.id == Call.channel_id).where(Channel.key == channel_key)

            calls = list(db.execute(cq).scalars().all())

            print(
                f"[truth] CACHE_ONLY start channel={channel_key or 'ALL'} "
                f"limit={limit} calls={len(calls)} max_hold={max_hold_sec}s prefer_seconds={prefer_seconds}"
            )

            ok = err = 0

            for call in calls:
                try:
                    entry_unix = _to_unix(call.started_at)

                    best_pool = cg.pick_best_pool_for_mint(call.mint, network="solana")
                    if not best_pool:
                        raise RuntimeError("no_pool_found")

                    ohlcv: list[list[float]] = []

                    if prefer_seconds:
                        cache = _ensure_seconds_cache(
                            db,
                            cg=cg,
                            call=call,
                            pool_address=best_pool.pool_address,
                            dex_id=best_pool.dex_id,
                            entry_unix=entry_unix,
                            max_hold_sec=max_hold_sec,
                        )
                        if cache and cache.data_gz and not cache.error:
                            ohlcv = load_cached_series(db, cache)

                    # fallback to minute cache warm
                    if not ohlcv:
                        mc = _ensure_minute_cache(
                            db,
                            cg=cg,
                            call=call,
                            pool_address=best_pool.pool_address,
                            dex_id=best_pool.dex_id,
                            entry_unix=entry_unix,
                            max_hold_sec=max_hold_sec,
                        )
                        if mc and mc.data_gz and not mc.error:
                            ohlcv = load_cached_series(db, mc)

                    if not ohlcv:
                        raise RuntimeError("ohlcv_empty")

                    ok += 1
                    print(
                        f"[truth] CACHE_ONLY ok call={call.id} mint={call.mint} "
                        f"pool={best_pool.dex_id}:{best_pool.pool_address[:8]}.. points={len(ohlcv)}"
                    )
                    time.sleep(sleep_s)

                except Exception as e:
                    err += 1
                    print(f"[truth] CACHE_ONLY ERROR call={call.id} mint={call.mint} err={str(e)[:280]}")
                    time.sleep(sleep_s)

            dt = time.time() - t0
            print(f"[truth] CACHE_ONLY done ok={ok} err={err} elapsed={dt:.2f}s")
            return

        # =========================================================
        # MODE 1: NORMAL TRUTH EVAL (StrategyResult)
        # =========================================================
        q = (
            select(StrategyResult, Call)
            .join(Call, Call.id == StrategyResult.call_id)
            .where(StrategyResult.strategy_key == strategy_key)
            .where(Call.status == "DONE")
            .where(StrategyResult.truth_checked_at.is_(None))
            .order_by(StrategyResult.id.desc())
            .limit(limit)
        )
        if channel_key:
            q = q.join(Channel, Channel.id == Call.channel_id).where(Channel.key == channel_key)

        rows = db.execute(q).all()

        print(
            f"[truth] start channel={channel_key or 'ALL'} "
            f"strategy={strategy_key} limit={limit} rows={len(rows)} max_hold={max_hold_sec}s"
        )

        ok = ambiguous = err = 0

        for sr, call in rows:
            try:
                entry_unix = _to_unix(call.started_at)

                tp_price = float(sr.entry_price_usd) * (1.0 + float(sr.tp_pct) / 100.0)
                sl_price = float(sr.entry_price_usd) * (1.0 - float(sr.sl_pct) / 100.0)

                best_pool = cg.pick_best_pool_for_mint(call.mint, network="solana")
                if not best_pool:
                    raise RuntimeError("no_pool_found")

                ohlcv: list[list[float]] = []

                if prefer_seconds:
                    cache = _ensure_seconds_cache(
                        db,
                        cg=cg,
                        call=call,
                        pool_address=best_pool.pool_address,
                        dex_id=best_pool.dex_id,
                        entry_unix=entry_unix,
                        max_hold_sec=max_hold_sec,
                    )
                    if cache and cache.data_gz and not cache.error:
                        ohlcv = load_cached_series(db, cache)

                if not ohlcv:
                    mc = _ensure_minute_cache(
                        db,
                        cg=cg,
                        call=call,
                        pool_address=best_pool.pool_address,
                        dex_id=best_pool.dex_id,
                        entry_unix=entry_unix,
                        max_hold_sec=max_hold_sec,
                    )
                    if mc and mc.data_gz and not mc.error:
                        ohlcv = load_cached_series(db, mc)

                if not ohlcv:
                    raise RuntimeError("ohlcv_empty")

                ev = _evaluate_from_ohlcv(
                    ohlcv,
                    tp_price=tp_price,
                    sl_price=sl_price,
                    entry_unix=entry_unix,
                    max_hold_sec=max_hold_sec,
                )

                if ev.outcome == "ERROR":
                    raise RuntimeError("eval_failed")

                sr.truth_outcome = ev.outcome
                sr.truth_exit_price_usd = ev.exit_price
                sr.truth_exit_t_sec = ev.exit_t_sec
                sr.truth_source = "coingecko_onchain"
                sr.truth_checked_at = datetime.now(timezone.utc)
                sr.truth_error = None

                db.commit()

                ok += 1
                if ev.outcome == "AMBIGUOUS":
                    ambiguous += 1

                print(
                    f"[truth] sr={sr.id} call={call.id} mint={call.mint} "
                    f"pool={best_pool.dex_id}:{best_pool.pool_address[:8]}.. "
                    f"outcome={ev.outcome} t={ev.exit_t_sec}"
                )
                time.sleep(sleep_s)

            except Exception as e:
                sr.truth_outcome = "ERROR"
                sr.truth_error = str(e)[:280]
                sr.truth_source = "coingecko_onchain"
                sr.truth_checked_at = datetime.now(timezone.utc)
                db.commit()

                err += 1
                print(f"[truth] ERROR sr={sr.id} call={call.id} mint={call.mint} err={sr.truth_error}")
                time.sleep(sleep_s)

        dt = time.time() - t0
        print(f"[truth] done ok={ok} ambiguous={ambiguous} err={err} elapsed={dt:.2f}s")


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser("TG-Channel-Lab Truth Job")
    p.add_argument("--channel", dest="channel_key", default=None, help="channels.key (e.g. seekrtrending)")
    p.add_argument("--strategy", dest="strategy_key", default="tp35_sl20", help="strategy_key or __cache_only__")
    p.add_argument("--limit", type=int, default=200, help="max rows to process")
    p.add_argument("--sleep", type=float, default=0.25, help="sleep between API calls")
    p.add_argument("--no-seconds", action="store_true", help="skip seconds OHLCV (use minute only)")
    p.add_argument("--max-hold", type=int, default=MAX_HOLD_SEC, help="holding window seconds")
    return p.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    run_truth_job(
        channel_key=args.channel_key,
        strategy_key=args.strategy_key,
        limit=args.limit,
        sleep_s=args.sleep,
        prefer_seconds=not args.no_seconds,
        max_hold_sec=args.max_hold,
    )
