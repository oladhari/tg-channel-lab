# CALL PATTERNS
**Source:** 3,820 real Telegram messages captured from 40 Solana meme coin channels.
All examples are actual messages stored in `calls.raw_message`.

---

## Pattern Taxonomy

Based on real captured messages, there are **6 distinct message formats** across the 40 channels.

---

### Pattern A — Minimal Bare CA

**Channels:** Any low-noise channel
**Frequency:** ~5% of messages

```
78xNg8Mzf3Ytwn9aan2tJSbrKxf717Dp4zR9RZSKpump
```

Or with token name:
```
The Top Is The Bottom   $BOTTOM

4gFChqYFAmJuLNPc6chW4NuMAqdJHi6gXww4XmVDpump

https://pump.fun/4gFChqYFAmJuLNPc6chW4NuMAqdJHi6gXww4XmVDpump
```

**Required:** CA (standalone on its own line or in pump.fun URL)
**Optional:** Token name, ticker, pump.fun link
**Assumptions:** CA is the only thing that matters; no supporting data
**Notes:** Often retweeted alerts or rapid fire calls from signal bots

---

### Pattern B — Seekr Trending Format

**Channel:** `seekrtrending`
**Frequency:** ~8% of total messages

```
{TOKEN_NAME} is now on Seekr Trending

CA: {MINT_ADDRESS}

Market Cap: ${VALUE}

Dexscreener Paid: ✅/❌
CTO: ✅/❌

{CATALYST — tweet text or description}

💡 Use GMGN to snipe on Telegram

👁️: {view_count}

Twitter Trending
```

**Required fields:** CA (after `CA: `), token name, market cap
**Optional:** Dexscreener paid status, CTO status, Twitter content, view count
**Key markers:** `is now on Seekr Trending`, `CA:`, `Market Cap:`

---

### Pattern C — MemesDontLies / KOL Signal Format

**Channels:** `memesdontlies`, `memecoincallsignal`, `kolsignal`
**Frequency:** ~20% of total messages

```
⚡️ {Token Name} ｜ ${TICKER}

🤴 CA: {MINT_ADDRESS}
🧢 MC:  {VALUE}k

👨‍🍳 Dev SOLD:  ✅/❌
👫 Holders:  {N} ｜ 💪 TOP 10:  {PCT}%

🔥🔥🔥{N} KOL BUY 🟢🟢

🌙 {wallet_short} ⇨ 📈 BUY {SOL_AMOUNT} SOL - {time_ago}
🌙 {wallet_short} ⇨ 📈 BUY {SOL_AMOUNT} SOL - {time_ago}

🎮 Total Volume:  ${VALUE} ｜ Txns: {N}
⏳ Age:  {time_ago}

🔗 Socials:  Twitter ｜ Telegram ｜ Website ｜ #{Ticker}

💦GMGN.AI (WEB) | NEO |GMGN.AI (BOT) | Trojan | Photon | AXIOM | Nova ｜ Bloom ｜ Padre ｜ AVE
```

**Required fields:** CA (after `CA: `), ticker, MC, KOL buy count
**Optional:** Dev sold status, holders, top 10%, KOL wallet details, volume, age, socials
**Key markers:** `⚡️`, `🤴 CA:`, `🧢 MC:`, `KOL BUY`, `Dev SOLD`

---

### Pattern D — MemesDontLies DYOR Format

**Channels:** `memesdontlies` (second message type), duplicated by `zorincalls`, `redbullcallz`
**Frequency:** ~25% of total messages

```
🔷 [SOL]   -   {Token Name}  ｜ ${TICKER}

🌖 CA: {MINT_ADDRESS}

┌ MC: ${VALUE} (ECA here) ｜ ⌛️ {age}
├ Curve:  {PCT}%
├ Liq:  ${VALUE}k
├ Volume:  ${VALUE}k ｜ 🅑 {buys} ｜ 🅢 {sells}
└ Social:  𝕏 ｜ Website

┌ Holders:  {N} ｜ TOP 10:  {PCT}%
├ Dev:  ✅ Sold All / ❌ Still Holds
├ DEX Paid: ✅/❌
├ Insiders: {PCT}%
├ Bundle: {PCT}%
├ Phishing: {PCT}%
├ Pro traders: {N}
└ {top10_pct_1} ｜ {top10_pct_2} ｜ ... ｜ {top10_pct_10}

┌ 🐦 Twitter Stats
├ 👥 Followers: {N}
├ 👤 Following: {N}
└ 👤 @{twitter_handle}

┌ 📊 Chart Activity
├ 👀 GMGN Views: {N}
└ 📈 Axiom Views: {N}

FAST BUY ｜ GMGN.AI (WEB) ｜ GMGN.AI (BOT) ｜ AXIOM ｜ Bloom

#DYOR #{Ticker} #Earlycalls
```

**Required fields:** CA (after `CA: `), [SOL] tag, MC, curve %, liquidity, volume, buys/sells
**Optional:** Dev status, DEX paid, insiders %, bundle %, Twitter stats, GMGN/Axiom views
**Key markers:** `🔷 [SOL]`, `🌖 CA:`, box-drawing chars `┌├└`, `ECA here`, `#DYOR`
**Richest format** — contains risk analysis (dev sold, bundle, insiders, phishing)

---

### Pattern E — RedBullCallz / Simple Alert Format

**Channels:** `redbullcallz`, `marksgems`, `rugpullsurvivorscall`
**Frequency:** ~15% of total messages

```
✅ Name: {Token Name}

👉 Ticker: ${TICKER}
🔗 Chain:  🟣 Sol

🔖 Contract Address:
{MINT_ADDRESS}

⌛️ Age : 0d 0h {N}m
💰 Current Market Cap : ${VALUE}

📊 Chart :
https://dexscreener.com/solana/{PAIR_ADDRESS}

Called by @{channel_name}
```

**Required fields:** CA (on own line after `Contract Address:`), chain (`🟣 Sol`), market cap, age
**Optional:** Dexscreener chart link, caller attribution
**Key markers:** `✅ Name:`, `🔖 Contract Address:`, `🟣 Sol`, `Called by @`

---

### Pattern F — China Pump / Narrative Format

**Channels:** `chinapumpcommunity`, `drakeetl`, `bat_gamble`
**Frequency:** ~10% of total messages (mixed languages)

```
74x, 1.33m - ${TICKER}

{narrative text, sometimes in Chinese}

CA: {MINT_ADDRESS}

https://gmgn.ai/sol/token/{GMGN_ID}_{MINT_ADDRESS}

Buy VIP signal: https://t.me/...
```

**Required fields:** CA (after `CA: ` or in GMGN URL)
**Optional:** Performance claims (74x, 1.33m), narrative, GMGN link
**Key markers:** `CA:`, `gmgn.ai/sol/token/`, performance text (`74x`, `1.33m`)
**Notes:** CA is often also embedded in the GMGN URL — this is the secondary entity URL extraction

---

## Common Elements Across All Patterns

### Contract Address Presentation
| Style | Example | Frequency |
|---|---|---|
| `CA: {MINT}` | `CA: GFik7LH45rq...pump` | ~45% |
| `Contract Address:` label then CA on next line | `🔖 Contract Address:\nGFik7LH...` | ~15% |
| Bare CA on own line | `GFik7LH45rq...pump` | ~20% |
| In pump.fun URL | `https://pump.fun/{MINT}` | ~10% |
| In GMGN URL | `gmgn.ai/sol/token/..._{MINT}` | ~10% |

### CA Suffix
All meme coins captured end in `pump` (pump.fun bonding curve tokens). The regex handles this with `(?:pump)?` optional suffix.

### Market Cap Notation
| Format | Example |
|---|---|
| Shorthand k | `22.5k`, `114.3k`, `21.2k` |
| Dollar + K | `$114.13K`, `$326,828.37` |
| Full number | `$81,627.94` |

### Age Notation
| Format | Example |
|---|---|
| Short | `0d 0h 6m`, `33m`, `2h 51m` |
| Relative | `30 minutes ago`, `3 hours ago` |

### Chain Identifiers
| Marker | Context |
|---|---|
| `[SOL]` | Pattern D header |
| `🟣 Sol` | Pattern E chain field |
| `#solana` | Hashtag at end |
| `pump` suffix on CA | Implicit Solana/pump.fun |
| `pumpswap` in DEX field | Graduated from bonding curve |

### DEX / Trading Bot Links Present
| Platform | Context |
|---|---|
| Dexscreener | Chart link or `Dexscreener Paid: ✅` |
| GMGN | `GMGN.AI (WEB)`, `GMGN.AI (BOT)`, gmgn.ai URL |
| Axiom | `AXIOM`, `Axiom Views` |
| Trojan | Sniper bot reference |
| Photon / Nova / Bloom / Padre / AVE / NEO / BananaGun | Sniper bot references |
| Birdeye | Referenced in some channels |

### Risk Flags (Pattern D only)
| Flag | Meaning |
|---|---|
| `Dev: ✅ Sold All` | Dev wallet cleared — positive signal |
| `Dev: ❌ Still Holds` | Dev still holding — risky |
| `DEX Paid: ✅` | Dexscreener page paid for — some legitimacy |
| `Bundle: X%` | % of supply bundled at launch — high = risky |
| `Insiders: X%` | Insider wallet % — high = risky |
| `Phishing: X%` | Flagged wallet % |
| `Curve: X%` | Bonding curve progress on pump.fun |

### Repeating Message Pattern (Same Token, Multiple Channels)
A single token commonly appears in **3-6 different channels within minutes**. Example from real data: `GFik7LH45rqwGjSp73zsnX4DPtx3G1opUqPEEuBApump` (Kirkski) appeared in `redbullcallz`, `zorincalls`, `seekrtrending`, `memesdontlies` almost simultaneously.

This is the **cross-channel signal confirmation** pattern — the more channels that call a token independently, the stronger the signal.
