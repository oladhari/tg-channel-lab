# Telegram Session Setup

Each service (listener, buyer, trader) requires its **own** Telegram session file.
Sharing the same session file causes `sqlite3.OperationalError: database is locked` and crashes buyer/trader in a restart loop.

Session files are stored in `./sessions/` on the host and mounted into containers:
```
sessions/
  tg_lab_session_listener.session
  tg_lab_session_buyer.session
  tg_lab_session_trader.session
```

> Sessions survive container restarts as long as the `./sessions/` folder exists on the host. You only need to do this once per service.

---

## Important: Non-interactive auth only

Telethon will crash with `EOFError` if it tries to prompt for input inside a Docker container. Always use the two-step method below (send code, then sign in) rather than running an interactive session.

---

## Step 1 — Send the login code to your phone

Replace `listener` with `buyer` or `trader` for the other sessions.

```bash
export TG_PHONE="+1234567890"

docker compose run --rm -T -e TG_PHONE="$TG_PHONE" listener python - <<'PY'
import os, asyncio
from telethon import TelegramClient

api_id   = int(os.environ["TELEGRAM_API_ID"])
api_hash = os.environ["TELEGRAM_API_HASH"]
d        = os.environ.get("TELEGRAM_SESSION_DIR", "/app/sessions")
name     = os.environ.get("TELEGRAM_SESSION_LISTENER", "tg_lab_session_listener")
path     = f"{d}/{name}.session"

async def main():
    c = TelegramClient(path, api_id, api_hash)
    await c.connect()
    sent = await c.send_code_request(os.environ["TG_PHONE"].strip())
    print("CODE_SENT_OK  phone_code_hash =", sent.phone_code_hash)
    await c.disconnect()

asyncio.run(main())
PY
```

For **buyer**, replace `listener` → `buyer` and `TELEGRAM_SESSION_LISTENER` → `TELEGRAM_SESSION_BUYER`.
For **trader**, replace `listener` → `trader` and `TELEGRAM_SESSION_LISTENER` → `TELEGRAM_SESSION_TRADER`.

---

## Step 2 — Sign in with the code you received

```bash
export TG_CODE="12345"
export TG_2FA_PASSWORD="your_2fa_password"   # leave empty string "" if no 2FA

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
d        = os.environ.get("TELEGRAM_SESSION_DIR", "/app/sessions")
name     = os.environ.get("TELEGRAM_SESSION_LISTENER", "tg_lab_session_listener")
path     = f"{d}/{name}.session"

async def main():
    c = TelegramClient(path, api_id, api_hash)
    await c.connect()
    if await c.is_user_authorized():
        me = await c.get_me()
        print("ALREADY_AUTH:", me.id, getattr(me, "username", None))
        await c.disconnect(); return
    sent = await c.send_code_request(os.environ["TG_PHONE"].strip())
    try:
        await c.sign_in(
            phone=os.environ["TG_PHONE"],
            code=os.environ["TG_CODE"],
            phone_code_hash=sent.phone_code_hash,
        )
    except SessionPasswordNeededError:
        pw = os.environ.get("TG_2FA_PASSWORD", "").strip()
        if not pw:
            raise SystemExit("2FA is enabled but TG_2FA_PASSWORD is empty.")
        await c.sign_in(password=pw)
    me = await c.get_me()
    print("AUTH_OK:", me.id, getattr(me, "username", None))
    await c.disconnect()

asyncio.run(main())
PY
```

Repeat both steps for **buyer** and **trader** by substituting the service name and session env var.

---

## Step 3 — Restart the service

```bash
docker compose up -d listener
docker compose logs -f --tail=30 listener
```

---

## Where to find your 2FA password

`TG_2FA_PASSWORD` is your **Telegram Two-Step Verification password**, set in:

> Telegram app → Settings → Privacy & Security → Two-Step Verification

It is not generated automatically — it is a password you chose yourself.

---

## Troubleshooting

**`database is locked` on buyer or trader startup:**
Check `.env` — each session var must point to a different file:
```env
TELEGRAM_SESSION_LISTENER=tg_lab_session_listener
TELEGRAM_SESSION_BUYER=tg_lab_session_buyer    # must NOT be tg_lab_session_listener
TELEGRAM_SESSION_TRADER=tg_lab_session_trader  # must NOT be tg_lab_session_listener
```

**`EOFError` during auth:**
You are running an interactive Telethon session inside Docker. Use the non-interactive two-step method above.

**Session breaks after container recreate:**
The `./sessions/` folder on the host must be mounted as a volume. Check `docker-compose.yml` — each service that uses sessions must have:
```yaml
volumes:
  - ./sessions:/app/sessions
```
