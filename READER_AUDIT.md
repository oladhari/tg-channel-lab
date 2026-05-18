# READER AUDIT
**Project:** TG Channel Lab — Telegram Meme Coin Signal Reader
**Scope:** Full pipeline from Telegram message → DB storage
**Based on:** Actual code + 3,820 real call records from 40 live channels

---

## 1. Project Structure

```
backend/app/
├── workers/
│   ├── run_listener.py       # Telegram → DB (signal ingestion)
│   ├── run_recorder.py       # Price polling, TP/SL detection, snapshots
│   ├── run_buyer_gmgn.py     # Buy via GMGN bot (Telegram)
│   ├── run_buyer_live.py     # Buy via Jito/Jupiter/Raydium on-chain
│   ├── run_trader_gmgn.py    # Sell via GMGN bot (Telegram)
│   ├── run_trader_live.py    # Sell via Jito/Jupiter/Raydium on-chain
│   ├── run_backfill.py       # Backfill downtime windows
│   └── pump_ws.py            # pump.fun WebSocket price cache
├── models/
│   ├── channel.py            # Channel config (username, TP/SL, amounts)
│   ├── call.py               # Token call record (entry, snapshot, live status)
│   ├── price_point.py        # Per-tick price history
│   ├── price_cross_event.py  # First-time TP/SL level crossings
│   ├── strategy_result.py    # Final outcome (TP/SL/TIME) per strategy
│   └── backfill_simulation.py# Simulated trades for missed signals
├── routes/
│   ├── channels.py           # CRUD + toggle endpoints
│   ├── calls.py              # List, detail, price history
│   ├── stats.py              # Paper stats, grid simulation, best strategy
│   └── live.py               # Live queue, wallet, history
└── utils/
    └── solana_ca.py          # CA regex utility (shared)
```

---

## 2. Where Things Happen

| Concern | File | Function / Line |
|---|---|---|
| Telegram connection | `run_listener.py:72` | `TelegramClient(SESSION_PATH, API_ID, API_HASH)` |
| Channel subscription | `run_listener.py:75-152` | `_subscribe_channel()` |
| Message parsing | `run_listener.py:32-52` | `extract_ca_from_event()` |
| CA regex | `run_listener.py:19-20` | `CA_REGEX` |
| CA extraction util | `utils/solana_ca.py:4-5` | `CA_REGEX`, `extract_first_solana_ca()` |
| Rejection / filtering | `run_listener.py:100-107` | `if not mint: return` |
| Deduplication | `models/call.py:24-26` | `UniqueConstraint(channel_id, mint)` |
| DB write | `run_listener.py:115-127` | `Call(...)`, `db.commit()` |
| Price polling | `run_recorder.py:366-415` | `record_tick()` |
| Entry price capture | `run_recorder.py:399-401` | `call.entry_price_usd = float(px)` |
| DEX snapshot | `run_recorder.py:403-412` | `_fetch_dex_snapshot()` |
| TP/SL detection | `run_recorder.py:552-596` | live_monitor_thread |
| Cross-level recording | `run_recorder.py:283-335` | `_check_and_record_crosses()` |
| Call finalization | `run_recorder.py:417-464` | `finalize_call()` |

---

## 3. End-to-End Pipeline

```
Telegram Channel Message
        │
        ▼
[run_listener.py] NewMessage event
        │
        ├─ extract_ca_from_event()
        │    ├─ Search message body text  (primary)
        │    └─ Search URL entities       (secondary — hyperlinked CAs)
        │
        ├─ No CA found → LOG [SKIP] → drop
        │
        ├─ CA found → Create Call(status=RECORDING, mint=CA, raw_message[:2000])
        │
        ├─ DB write → UniqueConstraint(channel_id, mint)
        │    └─ Duplicate → rollback, LOG [DUP] → drop
        │
        ▼
[run_recorder.py] Polling loop (every 2-5s)
        │
        ├─ record_tick() per active RECORDING call
        │    ├─ Price from pump.fun WS cache (200ms, zero cost)
        │    ├─ Fallback: Dexscreener + Jupiter in parallel (HTTP)
        │    ├─ No price after 30s → status = IGNORED_NO_PRICE
        │    └─ First price → entry_price_usd set + _fetch_dex_snapshot()
        │
        ├─ _write_price_point()       → PricePoint row (t_sec, price_usd, source)
        ├─ _check_and_record_crosses() → PriceCrossEvent for each new level crossed
        │
        ├─ Live Monitor Thread (200ms, parallel)
        │    └─ For calls with live_buy_status=SENT:
        │         ├─ Detect per-channel TP/SL
        │         ├─ finalize_call(set_done=False) on hit
        │         └─ Update live_sell_status = SENT
        │
        ├─ Duration elapsed (1500s) → finalize_call(set_done=True)
        │    └─ Compute StrategyResult (tp35_sl20 key, outcome, pnl_pct)
        │         Call.status = DONE
        │
        ▼
Database (PostgreSQL)
  calls → price_points → price_cross_events → strategy_results
```

---

## 4. Channels in Production

**Total:** 40 channels, all enabled, all Solana meme coin callers.
**Live trading enabled:** 1 (`rugpullsurvivorscall`, TP=80%, SL=25%)
**TP/SL overrides set:** 1 channel only (rest use global defaults)

| Category | Channels (sample) |
|---|---|
| Alpha / Early calls | `mattprintalphacalls`, `alphakollswithins`, `alphakingsol`, `earlybirdtg` |
| Meme / degen | `memesdontlies`, `memecoinpumps300x`, `memecoincallsignal`, `wesendingshit` |
| Trending scanners | `seekrtrending`, `cto_scanner`, `tradersviewtrenches` |
| KOL / signal | `kolsignal`, `deezesignal`, `zen_call`, `minegems` |
| Community | `rugpullsurvivorscall`, `gemhunters_off`, `kingdomofdegencalls` |

---

## 5. Database Stats (as of audit)

| Status | Count |
|---|---|
| DONE (25-min recording completed) | 3,499 |
| RECORDING (active) | 12 |
| IGNORED_NO_PRICE (no price in 30s) | 309 |
| **Total** | **3,820** |

- **IGNORED_NO_PRICE rate:** 309 / 3,820 = **8.1%** — tokens where no DEX price was ever found (likely pre-listing or dead tokens)

---

## 6. Price Recording Strategy

| Phase | Duration | Min Gap | Source |
|---|---|---|---|
| Burst mode | First 300s (5 min) | 200ms | pump.fun WS + HTTP fallback |
| Normal mode | After 300s | 2.0s | pump.fun WS + HTTP fallback |
| Fast polling | First 120s | 2s loop | Controls main loop speed |
| Slow polling | After 120s | 5s loop | Controls main loop speed |

**Circuit breaker:** After 5 consecutive HTTP failures for a mint, pause HTTP for 30s. pump.fun WS still works.

---

## 6. Known Limitations

1. **Only one CA extracted per message** — if a message mentions two tokens, only the first match is used.
2. **No message-level validation** — no check that the message actually looks like a call (keywords, format). Any message with a CA is accepted.
3. **Symbol derived from mint only** — `symbol = mint[:6]`. Real token symbol/name from message is not parsed.
4. **No chain validation** — EVM addresses (0x...) can't match the BASE58 regex, so Solana-only is implicit but not explicit.
5. **IGNORED_NO_PRICE at 8.1%** — pre-listing tokens, scam tokens, or tokens not yet on DEX when called.
6. **SeenMint model exists but is unused** — `seen_mints` table has `(channel_id, mint)` unique constraint but is not populated by any current worker.
