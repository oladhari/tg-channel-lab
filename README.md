# TG Channel Lab

A research and automated trading system for Solana token calls from Telegram channels.

**What it does:**
- Listens to Telegram channels in real-time
- Detects Solana token mint addresses from messages
- Records price history for each token call
- Simulates TP/SL trading strategies (paper trading)
- Shows channel performance stats on a dashboard
- Optionally executes live trades via GMGN bot or direct on-chain swaps (Jupiter/Raydium)

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

# Session names (leave as-is unless you need multiple accounts)
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

# Strategy thresholds
DISPLAY_TP_PCT=35
DISPLAY_SL_PCT=20
SIM_TP_PCT=35.0
SIM_SL_PCT=20.0
PAPER_ENTRY_SOL=0.1

# GMGN live trading (optional — leave empty to disable)
GMGN_TARGET=
GMGN_SELL_PERCENT=100%
GMGN_BUY_COOLDOWN_SEC=15
GMGN_SELL_COOLDOWN_SEC=45

# Live Solana trading (optional — leave empty to disable)
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

You need to create a `.session` file for each Telegram account (listener, buyer, trader). This is done once. The session files are saved locally and reused on every restart.

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

Repeat the same two steps for the **buyer** and **trader** sessions by replacing `listener` with `buyer` or `trader` in the `docker compose run` command, and replacing `TELEGRAM_SESSION_LISTENER` with `TELEGRAM_SESSION_BUYER` or `TELEGRAM_SESSION_TRADER`.

> Session files are saved in `./sessions/` on your machine. As long as that folder exists, you never need to authenticate again.

### 4. Start the app

```bash
docker compose up -d
```

This starts all services in the background:
- `db` — PostgreSQL database
- `api` — FastAPI backend (port 8000)
- `frontend` — Next.js dashboard (port 3000)
- `listener` — Telegram channel listener
- `recorder` — Price recording worker
- `buyer` — GMGN buy worker
- `trader` — GMGN sell worker

### 5. Open the dashboard

```
http://localhost:3000
```

Add your first Telegram channel from the UI and the listener will start monitoring it immediately.

---

## Common Commands

```bash
# Start everything
docker compose up -d

# Stop everything
docker compose down

# View logs for all services
docker compose logs -f

# View logs for a specific service
docker compose logs -f listener
docker compose logs -f recorder
docker compose logs -f buyer
docker compose logs -f trader

# Restart a single service
docker compose restart listener

# Rebuild after code changes
docker compose up -d --build

# Check running containers
docker compose ps
```

---

## Services Overview

| Service | Description | Port |
|---------|-------------|------|
| `db` | PostgreSQL 16 database | internal |
| `api` | FastAPI REST backend | 8000 |
| `frontend` | Next.js dashboard | 3000 |
| `listener` | Monitors Telegram channels, detects mint addresses | — |
| `recorder` | Polls token prices, computes TP/SL outcomes | — |
| `buyer` | Sends buy commands to GMGN bot | — |
| `trader` | Sends sell commands to GMGN bot | — |
| `buyer-live` | Direct on-chain buys via Jupiter/Raydium (optional) | — |
| `trader-live` | Direct on-chain sells via Jupiter/Raydium (optional) | — |

> `buyer-live` and `trader-live` are disabled by default. Enable them in `docker-compose.yml` if you want direct on-chain execution.

---

## Troubleshooting

**Listener not detecting channels after adding from UI:**
The listener loads channels once at startup. Restart it after adding a new channel:
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

## Project Structure

```
tg-channel-lab/
├── backend/
│   ├── app/
│   │   ├── workers/        # listener, recorder, buyer, trader
│   │   ├── executors/      # Jupiter and Raydium swap executors
│   │   ├── models/         # SQLAlchemy ORM models
│   │   ├── routes/         # FastAPI endpoints
│   │   └── services/       # Price APIs (Dexscreener, etc.)
│   └── requirements.txt
├── frontend/               # Next.js dashboard
├── sessions/               # Telegram session files (gitignored)
├── scripts/                # Session setup scripts
├── docker-compose.yml
└── .env                    # Your secrets (gitignored)
```

---

## Known Issues Being Fixed

- Direct Jupiter/Raydium trading has timeout and type errors — workaround is GMGN bot mode
- Price recording uses Dexscreener which can be slow — migration to Jupiter Price API planned
- Listener requires restart when new channels are added from the UI
