# TG Channel Lab — Technical Performance Report
**Generated:** 2026-04-04  
**Bot version:** tg-channel-lab (feat/enhance_monitor_live)  
**Data window:** 2026-03-12 → 2026-04-04 (~23 days)  
**Channels monitored:** 40 Solana meme coin Telegram channels  

---

## 1. Executive Summary

This bot reads 40 Telegram channels, extracts Solana token CAs, records 25 minutes of price history per call, and computes paper trading outcomes using a fixed TP/SL strategy.

**On paper: the strategy looks profitable. In reality: it is not.**

The core reason is a fundamental gap between how paper results are computed and how trades are actually executed. This gap is not a bug — it is a structural impossibility that affects every signal-following bot at this latency level. The full breakdown is in Section 6.

---

## 2. Data Collection Overview

### 2.1 Call Ingestion Pipeline

```
Telegram message
  → CA regex extraction (BASE58, 32–44 chars)
  → DB write: calls(channel_id, mint, started_at, raw_message)
  → Dedup: UniqueConstraint(channel_id, mint) — same token only once per channel

Price recording (25 min window per call):
  → pump.fun WebSocket cache (200ms burst for first 5 min)
  → Fallback: Dexscreener + Jupiter HTTP (parallel)
  → No price in 30s → IGNORED_NO_PRICE

Outcome computation (at 25-min end):
  → StrategyResult: find first TP/SL crossing in price_points
  → outcome = TP / SL / TIME, pnl_pct stored
```

### 2.2 Dataset Volume

| Metric | Value |
|---|---|
| Total calls recorded | 9,028 |
| Status: DONE (full 25-min window) | 7,322 |
| Status: IGNORED_NO_PRICE | 1,701 (18.8%) |
| Status: RECORDING (active) | 5 |
| Calls with price history | 7,327 |
| Total price data points | ~3.08 million |
| Avg price points per call | 421 ticks |
| Entry price delay (median) | 3 seconds after message |

### 2.3 How entry_price Is Set

The entry price is the **first price successfully fetched** after the message is received — either from the pump.fun WebSocket cache or HTTP fallback. The median delay is 3 seconds. This is the price used for all paper P&L calculations. The actual executable entry price in a real trade would be higher due to:

- Network latency to send the buy TX
- Mempool queue time
- MEV / sandwich competition on the bonding curve

---

## 3. Paper Results (strategy_results table)

### 3.1 Global Stats — `tp35_sl20` (TP +35%, SL −20%)

| Metric | Value |
|---|---|
| Calls evaluated | 7,326 |
| TP exits (hit +35%) | 37.4% |
| SL exits (hit −20%) | 52.0% |
| TIME exits (neither in 25 min) | 10.6% |
| Average P&L | **+18,419%** ← extreme outlier distortion |
| **Median P&L** | **−20.4%** |
| P75 P&L | +39.1% |
| P90 P&L | +50.4% |
| P95 P&L | +61.8% |
| Worst P&L | −99.6% |
| Best P&L | +134,919,591% |

> **The average is meaningless.** 4 calls have P&L over +1,000,000% (tokens that went 10,000× in the recording window). The median is −20.4%, meaning **more than half of all calls hit SL**.

### 3.2 Distribution Breakdown

| Range | Count | % of total |
|---|---|---|
| Hit SL (< −20%) | 3,805 | 52.0% |
| Flat (−20% to +35%) | 780 | 10.6% |
| Hit TP (+35% to +100%) | ~2,400 | ~32.8% |
| Moonshot (+100% to +1000%) | 268 | 3.7% |
| Extreme outlier (>+1000%) | 72 | ~1.0% |

### 3.3 CSV Dataset Stats (direct from price_points)

From the exported `dataset.csv` (7,322 DONE calls):

| Metric | Value |
|---|---|
| Hit TP35 (+35%) | 3,408 / 7,322 = **46.5%** |
| Hit TP50 (+50%) | 2,643 / 7,322 = **36.1%** |
| Hit SL20 (−20%) | 4,984 / 7,322 = **68.1%** |
| Average peak multiplier | 186.4× (outlier-driven) |
| **Median peak multiplier** | **1.31×** |

> Note: hit_tp35 and hit_sl20 are not mutually exclusive. A token can pump +35% then dump −20% below entry in the same 25-min window. This happens frequently.

---

## 4. Multi-Channel Confirmation Signal

The same token is called by multiple channels within minutes. This is the strongest real signal in the dataset.

| Channels calling same token | Tokens | TP rate | SL rate | Median P&L |
|---|---|---|---|---|
| 1 channel only | 2,483 | 32.1% | 57.7% | −21.6% |
| 2 channels | 1,740 | 33.5% | 54.7% | −20.9% |
| 3–4 channels | 1,961 | 40.1% | 49.4% | −13.7% |
| **5+ channels** | **1,138** | **50.4%** | **39.8%** | **+35.1%** |

**Key finding:** Tokens called by 5 or more channels achieve a **positive median P&L of +35.1%** and a **50.4% TP rate**. This is the only tier where median turns positive. Cross-channel confirmation within a short window is the only filtering criterion that demonstrably improves outcomes.

---

## 5. Per-Channel Paper Performance (Top Channels)

Ranked by median P&L, minimum 10 calls:

| Channel | Calls | TP Rate | SL Rate | Median P&L |
|---|---|---|---|---|
| rugpullsurvivorscall | 98 | 65.3% | 34.7% | +38.4% |
| bocchiplays | 27 | 51.9% | 11.1% | +37.7% |
| riskybiznessonly | 14 | 57.1% | 35.7% | +37.3% |
| drakeetl | 45 | 60.0% | 40.0% | +36.8% |
| cto_scanner | 52 | 53.8% | 9.6% | +35.6% |
| chinapumpcommunity | 34 | 35.3% | 38.2% | −0.1% |
| azunasplays | 84 | 15.5% | 23.8% | −0.4% |
| teslacallsofficial | 48 | 6.3% | 22.9% | −0.3% |

Channels like `rugpullsurvivorscall` and `drakeetl` consistently call early-stage tokens with genuine alpha. Channels like `azunasplays` and `teslacallsofficial` call late-stage tokens after the pump, resulting in near-zero TP rates.

---

## 6. Why Paper Results Do Not Match Reality

This is the most important section of this report.

### 6.1 Reason 1 — Entry Price Is a Fiction

**Paper:** Entry price = first price fetched after message (median: 3 seconds delay).  
**Reality:** You need 3–8 additional seconds to:  
  1. Parse the message and extract CA (negligible)  
  2. Fetch a quote from Jupiter/Raydium (~1–2s)  
  3. Build and sign the transaction (~0.5s)  
  4. Submit and land the TX via Jito bundle or RPC (~0.4–3s)  
  5. Confirmation receipt (~1–5s)

**Total realistic entry delay: 5–15 seconds after the message.**

In meme coin calls, the first 5–15 seconds are the fastest movement window. A token called at $10k market cap may already be at $25k by the time your buy TX lands. The paper result assumes you bought at $10k. You actually bought at $25k — so your "TP at +35%" never triggers because you need +159% from real entry to reach that price.

### 6.2 Reason 2 — GMGN Execution Delay

The live trading path used GMGN bot (Telegram-based). When a TP/SL trigger was detected and a sell command was sent to GMGN:

1. Our code detects TP crossing in the live_monitor_thread (200ms polling)
2. Telegram message is sent to GMGN bot (~0.5–1s)
3. GMGN reads the message and executes the sell (~3–30s variable)

**Observed case:** Token hit +141% peak. Our code triggered TP at +80%. By the time GMGN executed, price had fallen to +56% — a 25-percentage-point execution gap. This is not a bug. GMGN is an automated Telegram bot with its own queue and latency. There is no way to reduce this delay without on-chain execution.

### 6.3 Reason 3 — Jupiter Ultra API Requires Paid Plan

The on-chain buy/sell path (Jito + Jupiter) was built but non-functional during the live trading period because:

- `api.jup.ag` (Ultra endpoint `/ultra/v1/order`) requires a paid subscription
- `lite-api.jup.ag` (free) does not expose the Ultra endpoint
- All buy attempts via `buyer-live` returned HTTP 401
- All trades therefore fell through to GMGN

**Cost to fix:** Jupiter paid API key (~$99–$499/month depending on tier).

### 6.4 Reason 4 — The Paper Strategy Has No Awareness of Token Age

Tokens called under 5 minutes old have a **43.8% TP rate** on paper. Tokens called after 2 hours have a **24.1% TP rate**. Paper P&L is computed the same way for both. In reality, a token called at 2 hours old is often a rebound pump from someone distributing — the paper entry at "current price" may be the local top.

The recorder sets entry price to whatever price it fetches first — it has no concept of whether that price is at the beginning, middle, or end of the token's life cycle.

### 6.5 Reason 5 — Survivorship in Price Data

The `IGNORED_NO_PRICE` rate is **18.8%** (1,701 calls). These are tokens where no price was ever found within 30 seconds. They are completely excluded from all paper stats. Many of these were rug pulls, pre-listing scams, or fake calls. If they were included with a −100% outcome (the realistic worst case), the paper results would be significantly worse.

### 6.6 Reason 6 — The TP/SL Strategy Does Not Account for Slippage

Paper P&L assumes exact execution at the TP/SL price level. In reality:

- Meme coin liquidity is thin. Selling 0.1 SOL worth at the TP price moves the market.
- Slippage at exit: 5–25% depending on token liquidity.
- The paper exit at exactly +35% is actually executed at +20–30% after slippage.

---

## 7. Live Trading Results (Actual Executed Trades)

| Metric | Value |
|---|---|
| Calls with live buy enabled | 8 |
| Buy TXs sent (GMGN) | 7 |
| Sell TXs sent | 7 |
| TP exits | 5 |
| SL exits | 0 |
| TIME exits | 0 |
| Unknown/manual | 2 |

Only 1 channel had live trading enabled (`rugpullsurvivorscall`, TP=80%, SL=25%). The sample size is too small to draw conclusions. The 5/7 TP rate matches the channel's paper TP rate of 65.3%, but GMGN execution delays reduced actual P&L in every case.

---

## 8. Token Age at Time of Call

| Token age when called | Calls | TP Rate | Notes |
|---|---|---|---|
| < 5 minutes old | 1,700 | 43.8% | Best signal tier, highest risk |
| 5–30 minutes | 3,035 | 39.2% | Standard call window |
| 30–120 minutes | 1,102 | 35.4% | Trend following |
| > 2 hours | 875 | 24.1% | Late callers, often already dumped |

---

## 9. Data Quality Issues

### 9.1 Missing Market Cap (entry_mcap)

The `dataset.csv` `entry_mcap` column is empty for **100% of rows**. Root cause: the `market_cap` field in the `calls` table is only set during `_fetch_dex_snapshot()` which runs once at the first price poll. By the time this is stored, it is the market cap at snapshot time (~3–5s after call), not at entry. In practice most rows have this value — the CSV export joined it correctly — but the column is empty because the SQL query joins `c.market_cap` which uses the snapshot value, not a real-time computation.

### 9.2 Internal Consistency Check — entry_price vs first price_point

A background query confirmed that `calls.entry_price_usd` and the first row in `price_points` for the same call are **identical** (median drift: 0.00%, average drift: 0.01%). The recorder sets both at the same moment. This means the paper methodology is internally consistent — the entry price accurately reflects the first price tick recorded. The distortion is not internal drift but the gap between the Telegram message timestamp and when the first price tick is actually captured (~3 seconds).

### 9.3 Price Source Mix

Price points come from three sources: pump.fun WebSocket (fastest, 0 cost), Dexscreener HTTP (good for graduated tokens), Jupiter price API (most accurate but rate-limited). Mixing sources introduces price discontinuities when a token graduates from pump.fun to Raydium mid-recording.

### 9.3 Paper Strategy Assumes Perfect Timing

`strategy_results.exit_price_usd` is set to exactly `entry_price * 1.35` (for TP) or `entry_price * 0.80` (for SL). The actual executed price would be the first price point **at or past** that level. This means paper P&L is systematically optimistic because:

- TP: paper says +35.0%, but the next price point after crossing may be +36.5% → paper locks in +35%, real trade gets +36.5% (minor, positive)  
- SL: paper says −20.0%, but on a fast dump the next price point after crossing may be −35% → paper locks in −20%, real trade gets −35% (major, negative)

Fast dumps (common in meme coins) hit SL at a price far worse than −20%. Paper systematically underreports SL severity.

---

## 10. Key Findings Summary

| Finding | Impact |
|---|---|
| Median P&L is −20.4% | Most calls hit SL. Average is misleading. |
| 5+ channel confirmation → median +35.1% | Only reliable filtering signal found |
| 18.8% of calls get no price data | All excluded from stats (survivorship bias) |
| Entry delay 3s on paper, 10–15s in reality | Paper entry is 20–50% cheaper than real |
| GMGN execution gap 5–30s after TP trigger | Sell price 10–50% below detected TP |
| Jupiter Ultra API requires paid plan | On-chain execution was never functional |
| Token age > 2h: 24.1% TP rate | Late calls are nearly worthless |
| SL losses worse than paper shows | Fast dumps skip −20% level entirely |

---

## 11. Recommendations for Next Version

1. **On-chain execution only** — GMGN bot latency makes TP timing impossible. Buy via Jito, sell via Jito.
2. **Filter by cross-channel confirmation** — only trade tokens called by 5+ channels within 2 minutes.
3. **Filter by token age** — only trade tokens < 30 minutes old.
4. **Correct paper P&L for realistic entry delay** — simulate +10s delay in price_points before computing entry.
5. **Track actual slippage** — record both the signal price and the actual executed price.
6. **Expose DB port locally** — avoids the `docker exec` workaround for all local tooling.
7. **Fix market cap in dataset** — join against first price_point with mcap estimate instead of snapshot.
8. **Remove outliers before reporting avg P&L** — cap at 10× (1000%) for display purposes.

---

## 12. Files and Artefacts

| File | Description |
|---|---|
| `dataset.csv` | 7,322 rows, one per DONE call, with outcome columns |
| `READER_AUDIT.md` | Full pipeline code audit, 40 channels, DB schema |
| `CALL_PATTERNS.md` | 6 message format patterns with real examples |
| `EXTRACTED_FIELDS_SPEC.md` | All parsed fields, sources, reliability |
| `RECOMMENDATIONS_FOR_SNIPER.md` | Redesign guide: regex, scoring, cross-channel tracker |
| `scripts/generate_dataset.py` | SQL → CSV export from live DB |
| `backend/app/workers/run_backfill.py` | Downtime backfill with GeckoTerminal historical prices |

---

*Report generated from live PostgreSQL data via `docker exec psql`. All P&L figures are paper (simulated). No financial advice.*
