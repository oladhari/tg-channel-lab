# RECOMMENDATIONS FOR SNIPER BOT
**Purpose:** Redesign a token sniper that currently catches nothing, based on real patterns
**Based on:** 3,820 real calls from 40 Solana meme coin channels

---

## Why Your Sniper Catches Nothing — Root Cause Diagnosis

Before recommendations, here is the most likely reason a sniper catches nothing when reading these channels:

1. **CA format mismatches.** The CA is rarely just a raw address. It appears as:
   - `CA: {MINT}pump` — with `pump` suffix baked in
   - On a line after `Contract Address:` label
   - Inside a `pump.fun/{MINT}pump` URL
   - Inside a `gmgn.ai/sol/token/..._{MINT}pump` URL
   - Embedded in message entities (hyperlinks), not visible in plain text

2. **Over-filtering at parse time.** If your sniper requires specific keywords before accepting a message, and those keywords vary by channel, you will silently drop valid calls.

3. **Wrong message field.** Some bots read `message.text` only. Telegram hyperlinks live in `message.entities`, not `message.text`. The CA may only exist in an entity URL.

4. **Deduplication too strict.** If your sniper deduplicates globally (same mint = skip), you lose the cross-channel confirmation signal, which is your best indicator.

5. **Too slow on first-message.** These channels are highly competitive. A call lives for 30-120 seconds before it's too late. If your sniper waits for 2+ signals before acting, it likely always misses.

---

## 1. Minimum Required Fields for a Valid Token Call

A token sniper should only require these **two fields** to consider a message a potential call:

| Field | How to Extract | Notes |
|---|---|---|
| **Mint address** | BASE58 regex (32-44 chars) + optional `pump` suffix | Solana-only implicit |
| **Source channel** | Telethon `event.chat_id` or channel username | Always known |

Everything else (MC, age, dev sold, etc.) is **enrichment** — fetch it after you have the CA.

---

## 2. Relaxed CA Extraction (Use This Exact Regex)

```python
import re

BASE58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
CA_RE  = re.compile(rf"(?<![{BASE58}])([{BASE58}]{{32,44}})(?:pump)?(?![{BASE58}])")

def extract_all_cas(text: str) -> list[str]:
    """Extract ALL Solana CAs from a text, not just the first."""
    return CA_RE.findall(text)

def extract_from_message(msg) -> list[str]:
    """Extract from body text AND entity URLs (Telegram hyperlinks)."""
    found = extract_all_cas(msg.message or "")
    for entity in (msg.entities or []):
        url = getattr(entity, "url", None)
        if url:
            found.extend(extract_all_cas(url))
    # Deduplicate while preserving order
    seen = set()
    return [ca for ca in found if ca not in seen and not seen.add(ca)]
```

**Important differences from current reader:**
- Returns **all CAs** in a message, not just the first
- Searches **both** body text and entity URLs (current reader does this — keep it)
- The `(?:pump)?` suffix is consumed so you get the base address without `pump`

---

## 3. Confidence Scoring Approach

Instead of binary accept/reject, score each signal 0-100:

### Scoring Dimensions

```python
def score_signal(mint: str, channel: str, message: str, all_channel_calls: dict) -> int:
    score = 0

    # === CA Quality (0-30) ===
    if mint.endswith("pump"):               # pump.fun token (most meme coins)
        score += 15
    if len(mint) == 44:                     # standard Solana address length
        score += 10
    if len(mint) >= 32:                     # minimum valid
        score += 5

    # === Channel Quality (0-20) ===
    # Assign each channel a tier based on your historical win rate
    tier = get_channel_tier(channel)        # 1=best, 3=worst
    score += {1: 20, 2: 10, 3: 5}.get(tier, 5)

    # === Cross-channel confirmation (0-30) ===
    # How many OTHER channels have called this mint in last 5 minutes?
    other_channels = count_recent_callers(mint, all_channel_calls, window_sec=300)
    score += min(30, other_channels * 10)   # +10 per extra channel, cap at 30

    # === Message richness (0-20) ===
    msg_lower = message.lower()
    if any(kw in msg_lower for kw in ["dev sold", "dev: ✅", "dev sold all"]):
        score += 8
    if any(kw in msg_lower for kw in ["kol buy", "kol"]):
        score += 5
    if "dex paid" in msg_lower and "✅" in message:
        score += 4
    if any(kw in msg_lower for kw in ["bundle:", "insiders:"]):
        score += 3  # channel provides risk data

    return min(100, score)
```

### Signal Tiers

| Score | Tier | Action |
|---|---|---|
| 0-29 | **Ignore** | No CA or known spam channel |
| 30-59 | **Possible call** | Log, maybe paper-trade |
| 60-79 | **High confidence** | Buy with small position |
| 80-100 | **Very high confidence** | Buy with full position |

---

## 4. Three-Tier Decision Framework

### Tier C — Ignore
```
NOT (CA found in body or entity URL)
→ IGNORE
```

```
Caller is a known ad/spam channel
→ IGNORE
```

```
Same CA was called by this channel less than 1 hour ago
→ IGNORE (channel repeat)
```

### Tier B — Possible Call (paper trade / small buy)
```
CA found
AND channel is enabled
AND no global dedup hit in last 5 minutes (or hit by only 1 other channel)
AND score >= 30
→ POSSIBLE CALL
```

### Tier A — High Confidence (full buy)
```
CA found
AND 2+ different channels called this CA within 5 minutes
OR
CA found AND channel is tier-1 (historically high win rate)
AND score >= 60
→ HIGH CONFIDENCE
```

---

## 5. Relaxed Parsing First, Strict Filtering Second

**DO NOT** apply strict filters at parse time. Apply them in a second step:

```
Step 1 — Parse (very loose):
  Input:  Telegram message
  Output: candidate = {mint, channel, timestamp, raw_message}
  Filter: ONLY reject if no CA found

Step 2 — Enrich (async, fast):
  Fetch from Dexscreener: entry_price, liquidity, age, pair_address
  Fetch from pump.fun:    bonding curve progress
  Parse raw_message:      dev_sold, bundle_pct, kol_count, market_cap

Step 3 — Score + Filter:
  Apply confidence score
  Apply business rules (min MC, max age, max bundle, etc.)
  Decide: IGNORE / PAPER / BUY
```

**Why this order matters:** If you filter at step 1, you will drop real calls from channels that have unusual formatting. If you enrich first then filter, you can apply consistent rules to all channels regardless of message format.

---

## 6. Key Rules to Implement

### Must-have rules (blocking)
```python
# Never buy a CA you cannot price within 15 seconds
if not await fetch_price(mint, timeout=15):
    return IGNORE

# Never buy a token with near-zero liquidity
if liquidity_usd < 1000:
    return IGNORE

# Never buy a signal older than 30 seconds
if signal_age_sec > 30:
    return IGNORE
```

### Recommended rules (configurable)
```python
# Skip if market cap already too high (entry too late)
if market_cap > 500_000:          # $500k MC = likely too late for 100x
    return IGNORE

# Skip if pump.fun curve already near 100% (about to graduate / dump)
if curve_pct > 95:
    return IGNORE

# Prefer dev-sold tokens (safer)
if not dev_sold:
    confidence_multiplier *= 0.7

# High bundle = early dump risk
if bundle_pct > 30:
    confidence_multiplier *= 0.5

# High insider % = coordinated pump likely
if insider_pct > 20:
    confidence_multiplier *= 0.6
```

---

## 7. Cross-Channel Confirmation (Most Powerful Signal)

Real data shows the same token is called by **3-6 channels within minutes**. This is the strongest indicator of a real call vs noise.

```python
class CrossChannelTracker:
    def __init__(self, window_sec: int = 300):
        self.window_sec = window_sec
        # mint → list of (channel, timestamp)
        self._calls: dict[str, list[tuple[str, float]]] = {}

    def record(self, mint: str, channel: str) -> int:
        """Record a call and return how many channels have called this mint."""
        now = time.time()
        calls = self._calls.setdefault(mint, [])

        # Prune old entries
        calls[:] = [(ch, ts) for ch, ts in calls if now - ts < self.window_sec]

        # Add if not already from this channel
        if channel not in {ch for ch, _ in calls}:
            calls.append((channel, now))

        return len(calls)

    def get_callers(self, mint: str) -> list[str]:
        now = time.time()
        calls = self._calls.get(mint, [])
        return [ch for ch, ts in calls if now - ts < self.window_sec]
```

**Recommended thresholds:**
| Callers in 5 min | Action |
|---|---|
| 1 | Wait, log, maybe paper trade |
| 2 | High confidence — buy with 50% position |
| 3+ | Very high confidence — buy with full position |

---

## 8. Fields to Parse from `raw_message`

You do NOT need to do this perfectly — use fuzzy matching:

```python
import re

def parse_message_fields(text: str) -> dict:
    """
    Loosely parse structured fields from any channel format.
    Returns None for any field not found — never fails.
    """
    fields = {}

    # Market cap — handle "22.5k", "$114.13K", "$81,627.94"
    mc_match = re.search(
        r'(?:mc|market.?cap)[:\s]*\$?([\d,]+\.?\d*)\s*([km]?)',
        text, re.IGNORECASE
    )
    if mc_match:
        val, unit = mc_match.group(1).replace(',', ''), mc_match.group(2).lower()
        val = float(val) * (1000 if unit == 'k' else 1_000_000 if unit == 'm' else 1)
        fields['market_cap'] = val

    # Age — "6m", "2h 51m", "30 minutes ago"
    age_match = re.search(r'(?:age|⌛)[:\s]*(?:0d\s*)?(?:(\d+)h\s*)?(?:(\d+)m)', text, re.IGNORECASE)
    if age_match:
        h = int(age_match.group(1) or 0)
        m = int(age_match.group(2) or 0)
        fields['age_minutes'] = h * 60 + m

    # Dev sold
    fields['dev_sold'] = bool(re.search(r'dev[:\s]*✅|dev sold all', text, re.IGNORECASE))

    # Bundle %
    bundle_match = re.search(r'bundle[:\s]*([\d.]+)%', text, re.IGNORECASE)
    if bundle_match:
        fields['bundle_pct'] = float(bundle_match.group(1))

    # KOL buys
    kol_match = re.search(r'(\d+)\s*kol\s*buy', text, re.IGNORECASE)
    if kol_match:
        fields['kol_buys'] = int(kol_match.group(1))

    # Ticker — "$TICKER" or "Ticker: $TICKER"
    ticker_match = re.search(r'\$([A-Z]{2,10})(?:\b)', text)
    if ticker_match:
        fields['ticker'] = ticker_match.group(1)

    return fields
```

---

## 9. Recommended Minimum Architecture for Sniper

```
Telegram Listener (Telethon userbot)
    ├── For each channel: subscribe to NewMessage
    └── On message:
          1. extract_all_cas(body + entity_urls)
          2. For each CA:
               a. cross_channel_tracker.record(mint, channel)
               b. callers = tracker.get_callers(mint)
               c. If callers >= 1:
                    → enrich_async(mint)   # fetch price, DEX snapshot
                    → parse_message_fields(raw_message)
                    → score = compute_score(...)
                    → if score >= threshold: execute_buy(mint, amount)
               d. Log everything (all CAs, all channels, all scores)

Async Enrichment Worker
    ├── fetch_price(mint)         # Dexscreener + Jupiter in parallel
    ├── fetch_snapshot(mint)      # liquidity, MC, age, buys/sells
    └── timeout: 5s max — if no price, skip

Buy Executor
    ├── Primary:  GMGN bot (currently working)
    └── Future:   Jito → Jupiter Ultra → Raydium
```

---

## 10. Common Mistakes to Avoid

| Mistake | Impact | Fix |
|---|---|---|
| Reading only `message.text` | Miss CAs in hyperlinks (~10% of calls) | Always scan `message.entities` too |
| Extracting only first CA | Miss multi-token messages | Use `findall` not `search` |
| Global dedup (mint = skip) | Lose cross-channel confirmation signal | Track per-channel, keep count |
| Filtering by keywords | Miss channels with different formats | Parse loose, filter strict |
| Waiting for 2nd signal | Signal window is 30-90s | Buy on 1 signal from tier-1 channels |
| Buying by market cap in message | Message MC is stale by read time | Always fetch fresh price from DEX |
| Ignoring `started_at` lag | `started_at` is DB write time, not message time | Use Telethon `message.date` for real timestamp |
| Symbol = `mint[:6]` | Useless for display/matching | Parse `$TICKER` from message |
| Hard-coded strategy key | Ignores per-channel settings | Use channel's `live_tp_pct` / `live_sl_pct` if set |
