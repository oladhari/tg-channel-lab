# EXTRACTED FIELDS SPECIFICATION
**Source:** Actual code + real messages from 40 channels, 3,820 calls

This document specifies every field currently extracted from Telegram messages and DEX APIs,
its source, reliability, and whether it is populated in practice.

---

## Fields Extracted From Telegram Message

These fields are parsed at listen time (`run_listener.py`).

| Field | DB Column | Source | How | Always Present? |
|---|---|---|---|---|
| Mint address | `calls.mint` | Message body or URL entity | `CA_REGEX` on body text, then on entity URLs | **Yes** (required) |
| Symbol | `calls.symbol` | `mint[:6]` — first 6 chars | Derived, not parsed from message | **Yes** but meaningless |
| Raw message | `calls.raw_message` | Message body | First 2000 chars stored as-is | **Yes** (if message has text) |
| Channel | `calls.channel_id` | DB lookup | FK to `channels` table | **Yes** |
| Timestamp | `calls.started_at` | Server default `now()` | Not from message timestamp — set at DB write time | **Yes** |

### What Is NOT Extracted From Messages

The following fields are visible in real messages but **not parsed**:

| Field in Message | Example | Parsed? | Why Not |
|---|---|---|---|
| Token name | `Kirkski`, `$BOTTOM` | ❌ No | Only `mint[:6]` used as symbol |
| Ticker / symbol | `$KIRKSKI`, `$Yahu` | ❌ No | Regex only finds CA |
| Market cap | `$114.13K`, `22.5k` | ❌ No | Fetched from DEX later |
| Age | `0d 0h 6m`, `33m` | ❌ No | Not stored |
| Dev sold | `Dev: ✅ Sold All` | ❌ No | Not stored |
| Bundle % | `Bundle: 27.7%` | ❌ No | Not stored |
| Insiders % | `Insiders: 0.1%` | ❌ No | Not stored |
| KOL buys | `2 KOL BUY 🟢🟢` | ❌ No | Not stored |
| Chain | `[SOL]`, `🟣 Sol` | ❌ No | Implicit Solana only |
| DEX paid | `DEX Paid: ✅` | ❌ No | Not stored |
| Volume (from message) | `$74.6k` | ❌ No | Fetched from DEX later |
| Curve % | `Curve: 89.3%` | ❌ No | Not stored |
| Holders | `132 holders` | ❌ No | Not stored |

---

## Fields Populated by Recorder (DEX Snapshot)

Captured once at entry — first successful price fetch from Dexscreener (`_fetch_dex_snapshot()`).

| Field | DB Column | Source | Always Present? | Notes |
|---|---|---|---|---|
| Entry price | `calls.entry_price_usd` | pump.fun WS or Dexscreener/Jupiter | ~92% | Missing for IGNORED_NO_PRICE calls |
| Pair address | `calls.pair_address` | Dexscreener token endpoint | ~70% | Null if not on DEX yet |
| DEX ID | `calls.dex_id` | Dexscreener | ~70% | `raydium`, `orca`, `pumpswap`, etc. |
| Pair created at | `calls.pair_created_at_ms` | Dexscreener | ~60% | Unix ms, pump.fun pairs often missing |
| Liquidity USD | `calls.liquidity_usd` | Dexscreener | ~70% | |
| FDV | `calls.fdv` | Dexscreener | ~65% | |
| Market cap | `calls.market_cap` | Dexscreener | ~65% | |
| Vol 5m | `calls.vol_m5` | Dexscreener | ~65% | |
| Vol 1h | `calls.vol_h1` | Dexscreener | ~65% | |
| Vol 6h | `calls.vol_h6` | Dexscreener | ~65% | |
| Vol 24h | `calls.vol_h24` | Dexscreener | ~65% | |
| Price change 5m | `calls.pc_m5` | Dexscreener | ~65% | |
| Price change 1h | `calls.pc_h1` | Dexscreener | ~65% | |
| Price change 6h | `calls.pc_h6` | Dexscreener | ~65% | |
| Price change 24h | `calls.pc_h24` | Dexscreener | ~65% | |
| Buys 5m | `calls.buys_m5` | Dexscreener | ~65% | |
| Sells 5m | `calls.sells_m5` | Dexscreener | ~65% | |
| Buys 1h | `calls.buys_h1` | Dexscreener | ~65% | |
| Sells 1h | `calls.sells_h1` | Dexscreener | ~65% | |

---

## Price History Fields

One row per price tick in `price_points` table.

| Field | Column | Source | Notes |
|---|---|---|---|
| Time (seconds) | `t_sec` | `elapsed = now - started_at` | 0 = signal received |
| Time (ms) | `t_ms` | Same, in milliseconds | Higher precision for burst mode |
| Price | `price_usd` | pump.fun WS or HTTP | Float, USD |
| Source | `source` | `"pump_ws"` or `"http"` | pump.fun WS = real-time |
| Recorded at | `recorded_at` | DB write time | UTC wall-clock |

**Burst mode:** First 300s at 200ms resolution = up to 1,500 price points in first 5 minutes.
**Normal mode:** 2s resolution = ~600 more over next 20 minutes.
**Total per call:** ~500-2,100 price points depending on token activity.

---

## TP/SL Cross Event Fields

One row per threshold crossing in `price_cross_events`. Never duplicated.

| Field | Column | Values | Notes |
|---|---|---|---|
| Call | `call_id` | FK to calls | |
| Time | `t_ms` | milliseconds since call start | |
| Price | `price_usd` | crossing price | |
| Event type | `event_type` | `"TP_CROSS"`, `"SL_CROSS"` | |
| Level | `level_pct` | TP: 20-100 step 5, SL: 10-50 step 5 | Float |
| Source | `source` | `"pump_ws"`, `"http"` | |

**Total levels watched:** 17 TP × 9 SL = 153 per call.
Used to compute the full strategy grid without re-scanning price history.

---

## Strategy Result Fields

One row per (call, strategy_key) in `strategy_results`. Final trade outcome.

| Field | Column | Values | Notes |
|---|---|---|---|
| Call | `call_id` | FK | |
| Strategy | `strategy_key` | `"tp35_sl20"`, `"tp80_sl25"`, etc. | |
| TP % | `tp_pct` | Float | |
| SL % | `sl_pct` | Float | |
| Entry price | `entry_price_usd` | Float | Same as `calls.entry_price_usd` |
| Exit price | `exit_price_usd` | Float | Price at TP/SL/TIME |
| Exit time | `exit_t_sec` | Integer | Seconds from call start to exit |
| Outcome | `outcome` | `"TP"`, `"SL"`, `"TIME"` | |
| PnL % | `pnl_pct` | Float | `(exit/entry - 1) * 100` |

**Note:** `strategy_key` uses GLOBAL TP/SL thresholds for computation, even if the channel has per-channel overrides. Channel-specific TP/SL only controls the sell trigger timing, not what gets stored in `strategy_key`.

---

## Backfill Simulation Fields

One row per missed signal in `backfill_simulations`.

| Field | Column | Values |
|---|---|---|
| Channel | `channel_id`, `channel_username` | |
| Mint | `mint` | |
| Detection time | `detected_at` | Telegram message timestamp |
| Entry price | `entry_price_usd` | First valid candle AFTER detection |
| Entry delay | `entry_delay_sec` | Seconds between detection and entry candle |
| Exit price | `exit_price_usd` | Price at TP/SL/TIME |
| Exit time | `exit_t_sec` | Seconds from detection |
| TP used | `tp_pct` | From CLI or env |
| SL used | `sl_pct` | From CLI or env |
| Result | `result` | `TP`, `SL`, `TIME`, `NO_DATA`, `NO_ENTRY` |
| PnL | `pnl_pct` | |
| Max profit | `max_profit_pct` | Peak unrealized gain |
| Max drawdown | `max_drawdown_pct` | Worst unrealized loss |

---

## Field Reliability Summary

| Category | Reliability | Notes |
|---|---|---|
| Mint address | 100% | Required — no call created without it |
| Raw message | ~99% | Null only if message had no text |
| Entry price | ~92% | 8.1% IGNORED_NO_PRICE |
| DEX snapshot fields | ~65-70% | Null for very new / unlisted tokens |
| Price history | ~92% | Only calls with entry price have ticks |
| Strategy results | ~92% | Only finalized (DONE) calls |
| Token name / symbol | 0% | NOT extracted from message — only `mint[:6]` |
| Risk fields (dev sold, bundle, etc.) | 0% | NOT extracted — only in `raw_message` |
| Message timestamp | 0% | `started_at` = DB write time, NOT message date |
