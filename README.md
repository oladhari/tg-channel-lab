# TG Channel Lab

A research and automated trading system for Solana token calls from Telegram channels.

**What it does:**
- Listens to Telegram channels in real-time and detects Solana token mint addresses
- Records price history for every call (25 min, adaptive 2s/5s polling + pump.fun WebSocket)
- Runs a full TP/SL grid simulation (153 combinations: TP 20→100%, SL 10→50%) per channel and surfaces the single best-performing strategy for each
- Dashboard ranks channels by their peak achievable balance (cached 5 min) — no more fixed tp35/sl20
- Executes live trades via GMGN bot (Telegram) or direct on-chain swaps (Jupiter → Raydium → GMGN fallback)
- Live Monitor page — auto-refreshing view of signal→buy timing, hold duration, PnL, and wallet balance; includes on-chain swap history from the public Solana RPC (no API key required) matched against bot calls by mint address
- Per-channel simulation page with configurable TP/SL grid and optional accurate OHLCV backtesting via GeckoTerminal
- Dashboard best-strategy computation is non-blocking (background thread + 5min cache) — page never times out

---

## Requirements

- [Docker](https://docs.docker.com/get-docker/) + [Docker Compose](https://docs.docker.com/compose/install/)
- A Telegram account (to listen to channels)
- Telegram API credentials (free, from [my.telegram.org](https://my.telegram.org))

---

## Quick Start (Local)

### 1. Copy and configure your environment file

```bash
cp .env.example .env
```

Open `.env` and fill in the required values:

```env
# Database (leave defaults or change password)
POSTGRES_DB=tg_lab
POSTGRES_USER=tg_lab
POSTGRES_PASSWORD=your_secure_password
DATABASE_URL=postgresql+psycopg://tg_lab:your_secure_password@db:5432/tg_lab

# Telegram API — get from https://my.telegram.org → API development tools
TELEGRAM_API_ID=12345678
TELEGRAM_API_HASH=abc123yourhashhere

# Each service must have its OWN session name pointing to a separate .session file
TELEGRAM_SESSION_LISTENER=tg_lab_session_listener
TELEGRAM_SESSION_BUYER=tg_lab_session_buyer
TELEGRAM_SESSION_TRADER=tg_lab_session_trader
TELEGRAM_SESSION_DIR=/app/sessions

# Recording settings
RECORD_DURATION_SEC=1500
POLL_FAST_SEC=120
POLL_FAST_INTERVAL_SEC=2
POLL_SLOW_INTERVAL_SEC=5
NO_PRICE_TIMEOUT_SEC=30

# Paper simulation entry size
PAPER_ENTRY_SOL=0.1

# Strategy key used by live traders (must match what the recorder produces)
LIVE_STRATEGY_KEY=tp35_sl20

# GMGN live trading (optional — leave empty to disable)
GMGN_TARGET=
GMGN_SELL_PERCENT=100%
GMGN_BUY_COOLDOWN_SEC=15
GMGN_SELL_COOLDOWN_SEC=45

# Live Solana trading (optional — requires SOLANA_PRIVATE_KEY)
SOLANA_RPC_URL=https://api.mainnet-beta.solana.com
SOLANA_PRIVATE_KEY=
LIVE_BUY_AMOUNT_SOL=0.1
LIVE_FAST_MODE=1

```

### 2. Create the sessions folder

```bash
mkdir -p sessions
```

### 3. Authenticate Telegram sessions (one-time only)

You need to create a `.session` file for each Telegram service (listener, buyer, trader). Each service must use its **own session file** — sharing the same file causes SQLite lock conflicts.

**Step 1 — Send the login code to your phone:**

```bash
export TG_PHONE="+1234567890"   # your Telegram phone number

docker compose run --rm -T -e TG_PHONE="$TG_PHONE" listener python - <<'PY'
import os, asyncio
from telethon import TelegramClient

api_id   = int(os.environ["TELEGRAM_API_ID"])
api_hash = os.environ["TELEGRAM_API_HASH"]
path     = f"{os.environ.get('TELEGRAM_SESSION_DIR','/app/sessions')}/{os.environ.get('TELEGRAM_SESSION_LISTENER','tg_lab_session_listener')}.session"

async def main():
    c = TelegramClient(path, api_id, api_hash)
    await c.connect()
    sent = await c.send_code_request(os.environ["TG_PHONE"].strip())
    print("Code sent. phone_code_hash =", sent.phone_code_hash)
    await c.disconnect()

asyncio.run(main())
PY
```

**Step 2 — Sign in with the code you received:**

```bash
export TG_CODE="12345"
export TG_2FA_PASSWORD="your_2fa_password"   # leave empty string if no 2FA

docker compose run --rm -T \
  -e TG_PHONE="$TG_PHONE" \
  -e TG_CODE="$TG_CODE" \
  -e TG_2FA_PASSWORD="$TG_2FA_PASSWORD" \
  listener python - <<'PY'
import os, asyncio
from telethon import TelegramClient
from telethon.errors import SessionPasswordNeededError

api_id   = int(os.environ["TELEGRAM_API_ID"])
api_hash = os.environ["TELEGRAM_API_HASH"]
path     = f"{os.environ.get('TELEGRAM_SESSION_DIR','/app/sessions')}/{os.environ.get('TELEGRAM_SESSION_LISTENER','tg_lab_session_listener')}.session"

async def main():
    c = TelegramClient(path, api_id, api_hash)
    await c.connect()
    if await c.is_user_authorized():
        me = await c.get_me()
        print("Already authorized:", me.id, getattr(me, "username", None))
        await c.disconnect(); return
    sent = await c.send_code_request(os.environ["TG_PHONE"].strip())
    try:
        await c.sign_in(phone=os.environ["TG_PHONE"], code=os.environ["TG_CODE"], phone_code_hash=sent.phone_code_hash)
    except SessionPasswordNeededError:
        await c.sign_in(password=os.environ.get("TG_2FA_PASSWORD",""))
    me = await c.get_me()
    print("Auth OK:", me.id, getattr(me, "username", None))
    await c.disconnect()

asyncio.run(main())
PY
```

Repeat both steps for the **buyer** and **trader** sessions — replace `listener` with `buyer` or `trader` in the `docker compose run` command, and replace `TELEGRAM_SESSION_LISTENER` with `TELEGRAM_SESSION_BUYER` or `TELEGRAM_SESSION_TRADER`.

> Session files are saved in `./sessions/` on your machine. As long as that folder exists, you never need to authenticate again.

### 4. Start the app

```bash
# Paper trading + GMGN-based live trading
docker compose up -d

# Full live trading (also starts buyer-live and trader-live for direct on-chain swaps)
docker compose --profile live up -d
```

This starts:
- `db` — PostgreSQL database
- `api` — FastAPI backend (port 8000)
- `frontend` — Next.js dashboard (port 3000)
- `listener` — Telegram channel listener
- `recorder` — Price recording + real-time TP/SL monitor
- `buyer` — GMGN fallback buy worker
- `trader` — GMGN fallback sell worker
- `buyer-live` *(--profile live)* — Direct on-chain buy via Jupiter/Raydium/Jito
- `trader-live` *(--profile live)* — Direct on-chain sell via Jupiter/Raydium/Jito

### 5. Open the dashboard

```
http://localhost:3000
```

Add your first Telegram channel from the UI — the listener starts monitoring it immediately.

The **Live Monitor** page (`/live`) shows real-time signal→buy timing, hold duration, PnL, and wallet balance with 3-second auto-refresh. It also has an **On-Chain Swap History** section that fetches actual blockchain swaps via the free native Solana RPC (no API key required), matches them to bot calls by mint address, and shows paper vs real PnL side by side.

---

## Finding Telegram Signal Channels

The app does not bundle a list of channels — what you monitor is entirely up to you.

A practical way to discover active Solana signal channels:

1. Open [GMGN.ai](https://gmgn.ai) and browse the **trending** or **new tokens** charts.
2. Click on any token that spiked early — check its "Smart Money" buyers.
3. Many early callers link their Telegram channel in their profile or trade notes.
4. Search Telegram directly for terms like `solana calls`, `solana gems`, or `memecoin alpha`.

Once you find a channel worth tracking, add it from the app's **Channels** UI page — no restart needed, the listener auto-detects it within 60 seconds.

> **Tip:** Start with 2–3 channels and let the dashboard surface their best TP/SL strategy after a few days of data before scaling up.

---

## Common Commands

```bash
# Start everything
docker compose up -d

# Start with direct on-chain trading
docker compose --profile live up -d

# Stop everything
docker compose down

# View logs for all services
docker compose logs -f

# View logs for a specific service
docker compose logs -f listener
docker compose logs -f recorder
docker compose logs -f buyer
docker compose logs -f trader
docker compose logs -f buyer-live
docker compose logs -f trader-live

# Restart a single service
docker compose restart listener

# Rebuild after code changes
docker compose up -d --build

# Check running containers
docker compose ps
```

---

## Services Overview

| Service | Description | Poll | Port |
|---------|-------------|------|------|
| `db` | PostgreSQL 16 database | — | internal |
| `api` | FastAPI REST backend | — | 8000 |
| `frontend` | Next.js dashboard | — | 3000 |
| `listener` | Monitors Telegram channels, detects mint addresses | event-driven | — |
| `recorder` | Polls token prices (pump.fun WS + Dexscreener + Jupiter), runs 200ms live TP/SL monitor | 2s/5s adaptive | — |
| `buyer` | GMGN fallback buy (when buyer-live fails or not enabled) | 1s | — |
| `trader` | GMGN fallback sell (when trader-live fails or not enabled) | 2s | — |
| `buyer-live` | Direct on-chain buy: Jito → Jupiter → Raydium → GMGN fallback | 1s | — |
| `trader-live` | Direct on-chain sell: Jito → Jupiter → Raydium → GMGN fallback | 2s | — |

---

## Live Trading Architecture

### Buy flow (when a signal arrives)

```
Telegram signal → listener → DB (RECORDING, live_buy_status=NONE)
  ↓
buyer-live picks it up (1s poll, max 5min age filter)
  ↓ try Jito bundle (fastest, ~400ms)
  ↓ fallback Jupiter (direct RPC)
  ↓ fallback Raydium
  ↓ fallback GMGN bot (Telegram send)
  → live_buy_status = SENT
```

### Sell flow (when TP/SL is hit)

```
recorder live-monitor thread (200ms) detects TP/SL
  → creates StrategyResult, marks outcome = TP/SL
  → recording continues for full 25min (for simulation accuracy)
  ↓
trader-live picks it up (2s poll)
  ↓ check token balance in wallet
  ↓ try Jito bundle
  ↓ fallback Jupiter
  ↓ fallback Raydium
  ↓ fallback GMGN bot
  → live_sell_status = SENT
```

### Price detection for TP/SL

The recorder runs two parallel processes:
- **200ms live-monitor thread**: checks pump.fun WebSocket cache first (zero cost, sub-second freshness for bonding-curve tokens), then HTTP fallback (rate-limited to 500ms/mint) for graduated tokens.
- **Main recording loop** (2s fast / 5s slow): records price points to DB for the full 25-min window.

Per-channel TP/SL thresholds can be set from the UI and override the recorder's built-in defaults (35% TP / 20% SL).

### Stale signal protection

Both `buyer-live` and `trader-live` skip signals older than `LIVE_MAX_SIGNAL_AGE_SEC` (default 5 min). This prevents buying into calls that were signalled while the bot was restarting.

---

## Deduplication

- **Same channel**: A token called twice in the same channel is ignored on the second occurrence. The DB constraint `(channel_id, mint)` enforces uniqueness per channel.
- **Cross-channel**: The same token called in multiple channels creates separate independent records — one per channel. Each channel's performance is tracked independently.
- The listener also extracts mint addresses from URL hyperlinks embedded in Telegram messages (not just message body text), to handle channels that hide the contract address in a link.

---

## Troubleshooting

**buyer or trader crashes with `database is locked`:**
Each service must use its own Telegram session file. Check your `.env`:
```env
TELEGRAM_SESSION_LISTENER=tg_lab_session_listener
TELEGRAM_SESSION_BUYER=tg_lab_session_buyer    # must differ from listener
TELEGRAM_SESSION_TRADER=tg_lab_session_trader  # must differ from listener
```
Then re-authorize the buyer/trader sessions (see Step 3).

**Listener not detecting a newly added channel:**
The listener auto-detects new channels every 60 seconds — no restart needed. If you need it immediately:
```bash
docker compose restart listener
```

**Session expired / unauthorized error:**
Re-run the authentication steps (Step 1 and 2 above) for the affected session.

**Database connection errors on startup:**
The DB takes a few seconds to initialize. Wait 10-15 seconds and retry:
```bash
docker compose restart api listener recorder
```

**Port 3000 already in use:**
Another process is using that port. Stop it or change the port in `docker-compose.yml`:
```yaml
ports:
  - "3001:3000"   # access at http://localhost:3001
```

---

## Documentation

Detailed guides are in the [`docs/`](docs/) folder:

| File | Contents |
|------|----------|
| [docs/telegram-sessions.md](docs/telegram-sessions.md) | Non-interactive session auth for listener, buyer, trader — step-by-step with troubleshooting |

---

## Project Structure

```
tg-channel-lab/
├── backend/
│   ├── app/
│   │   ├── workers/        # listener, recorder, buyer, trader (gmgn + live)
│   │   ├── executors/      # Jupiter, Raydium, Jito swap executors
│   │   ├── models/         # SQLAlchemy ORM models
│   │   ├── routes/         # FastAPI endpoints (calls, channels, live, stats)
│   │   └── services/       # Price APIs, pump.fun WebSocket
│   └── requirements.txt
├── frontend/               # Next.js dashboard
│   └── src/app/
│       ├── page.tsx        # Main dashboard + wallet panel
│       ├── live/           # Live Monitor (auto-refresh, signal timing)
│       └── calls/          # Call detail pages
├── sessions/               # Telegram session files (gitignored)
├── docker-compose.yml
└── .env                    # Your secrets (gitignored)
```
