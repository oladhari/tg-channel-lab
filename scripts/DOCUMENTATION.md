# ✅ Documentation: Fix Telegram session (per service)

> These commands are meant to be saved in documentation and **NOT committed** (your `.env` and secrets stay gitignored).

## Preconditions (already in your containers)

* `TELEGRAM_API_ID`, `TELEGRAM_API_HASH`
* `TELEGRAM_SESSION_DIR=/app/sessions`
* `TELEGRAM_SESSION_LISTENER`, `TELEGRAM_SESSION_BUYER`, `TELEGRAM_SESSION_TRADER`

## Recommended: ensure sessions persist

On host:

```bash
ls -la sessions
```

You must see session files like:

* `sessions/tg_lab_session_listener.session`
* `sessions/tg_lab_session_buyer.session`
* `sessions/tg_lab_session_trader.session`

If sessions are not persistent, they’ll “break again” after container recreate.

---

## A) Listener session (non-interactive)

### 1) Ask Telegram to send the code

```bash
export TG_PHONE="+81XXXXXXXXXXX"

docker compose run --rm -T -e TG_PHONE="$TG_PHONE" listener python - <<'PY'
import os, asyncio
from telethon import TelegramClient

api_id = int(os.environ["TELEGRAM_API_ID"])
api_hash = os.environ["TELEGRAM_API_HASH"]
d = os.environ.get("TELEGRAM_SESSION_DIR","/app/sessions")
name = os.environ.get("TELEGRAM_SESSION_LISTENER","tg_lab_session_listener")
path = f"{d}/{name}.session"
phone = os.environ["TG_PHONE"].strip()

async def main():
    c = TelegramClient(path, api_id, api_hash)
    await c.connect()
    sent = await c.send_code_request(phone)
    print("CODE_SENT_OK phone_code_hash=", sent.phone_code_hash)
    await c.disconnect()

asyncio.run(main())
PY
```

### 2) Sign in (code + 2FA password)

```bash
export TG_CODE="12345"
export TG_2FA_PASSWORD="YOUR_2FA_PASSWORD"

docker compose run --rm -T \
  -e TG_PHONE="$TG_PHONE" \
  -e TG_CODE="$TG_CODE" \
  -e TG_2FA_PASSWORD="$TG_2FA_PASSWORD" \
  listener python - <<'PY'
import os, asyncio
from telethon import TelegramClient
from telethon.errors import SessionPasswordNeededError

api_id = int(os.environ["TELEGRAM_API_ID"])
api_hash = os.environ["TELEGRAM_API_HASH"]
d = os.environ.get("TELEGRAM_SESSION_DIR","/app/sessions")
name = os.environ.get("TELEGRAM_SESSION_LISTENER","tg_lab_session_listener")
path = f"{d}/{name}.session"

phone = os.environ["TG_PHONE"].strip()
code = os.environ["TG_CODE"].strip()
pw = os.environ.get("TG_2FA_PASSWORD","").strip()

async def main():
    c = TelegramClient(path, api_id, api_hash)
    await c.connect()

    if await c.is_user_authorized():
        me = await c.get_me()
        print("ALREADY_AUTH:", me.id, getattr(me,"username",None))
        await c.disconnect(); return

    sent = await c.send_code_request(phone)
    print("CODE_REQUEST_OK phone_code_hash=", sent.phone_code_hash)

    try:
        await c.sign_in(phone=phone, code=code, phone_code_hash=sent.phone_code_hash)
    except SessionPasswordNeededError:
        if not pw:
            raise SystemExit("2FA enabled but TG_2FA_PASSWORD is empty.")
        await c.sign_in(password=pw)

    me = await c.get_me()
    print("AUTH_OK:", me.id, getattr(me,"username",None))
    await c.disconnect()

asyncio.run(main())
PY
```

### 3) Restart service

```bash
docker compose up -d listener
docker compose logs -f --tail=80 listener
```

---

## B) Buyer session (worked ✅)

Exactly the same, but use `buyer` service and `TELEGRAM_SESSION_BUYER`:

```bash
docker compose run --rm -T \
  -e TG_PHONE="$TG_PHONE" \
  -e TG_CODE="$TG_CODE" \
  -e TG_2FA_PASSWORD="$TG_2FA_PASSWORD" \
  buyer python - <<'PY'
import os, asyncio
from telethon import TelegramClient
from telethon.errors import SessionPasswordNeededError

api_id = int(os.environ["TELEGRAM_API_ID"])
api_hash = os.environ["TELEGRAM_API_HASH"]
d = os.environ.get("TELEGRAM_SESSION_DIR", "/app/sessions")
name = os.environ.get("TELEGRAM_SESSION_BUYER", "tg_lab_session_buyer")
path = f"{d}/{name}.session"

phone = os.environ["TG_PHONE"].strip()
code = os.environ["TG_CODE"].strip()
pw = os.environ.get("TG_2FA_PASSWORD", "").strip()

async def main():
    client = TelegramClient(path, api_id, api_hash)
    await client.connect()

    if await client.is_user_authorized():
        me = await client.get_me()
        print("ALREADY_AUTH:", me.id, getattr(me, "username", None))
        await client.disconnect()
        return

    sent = await client.send_code_request(phone)
    print("CODE_REQUEST_OK phone_code_hash=", sent.phone_code_hash)

    try:
        await client.sign_in(phone=phone, code=code, phone_code_hash=sent.phone_code_hash)
    except SessionPasswordNeededError:
        if not pw:
            raise SystemExit("2FA enabled but TG_2FA_PASSWORD is empty.")
        await client.sign_in(password=pw)

    me = await client.get_me()
    print("AUTH_OK:", me.id, getattr(me, "username", None))
    await client.disconnect()

asyncio.run(main())
PY
```

Restart:

```bash
docker compose up -d buyer
docker compose logs -f --tail=80 buyer
```

---

## C) Trader session (same method)

Same script but run on `trader` and use `TELEGRAM_SESSION_TRADER`:

```bash
docker compose run --rm -T \
  -e TG_PHONE="$TG_PHONE" \
  -e TG_CODE="$TG_CODE" \
  -e TG_2FA_PASSWORD="$TG_2FA_PASSWORD" \
  trader python - <<'PY'
import os, asyncio
from telethon import TelegramClient
from telethon.errors import SessionPasswordNeededError

api_id = int(os.environ["TELEGRAM_API_ID"])
api_hash = os.environ["TELEGRAM_API_HASH"]
d = os.environ.get("TELEGRAM_SESSION_DIR", "/app/sessions")
name = os.environ.get("TELEGRAM_SESSION_TRADER", "tg_lab_session_trader")
path = f"{d}/{name}.session"

phone = os.environ["TG_PHONE"].strip()
code = os.environ["TG_CODE"].strip()
pw = os.environ.get("TG_2FA_PASSWORD", "").strip()

async def main():
    client = TelegramClient(path, api_id, api_hash)
    await client.connect()

    if await client.is_user_authorized():
        me = await client.get_me()
        print("ALREADY_AUTH:", me.id, getattr(me, "username", None))
        await client.disconnect()
        return

    sent = await client.send_code_request(phone)
    print("CODE_REQUEST_OK phone_code_hash=", sent.phone_code_hash)

    try:
        await client.sign_in(phone=phone, code=code, phone_code_hash=sent.phone_code_hash)
    except SessionPasswordNeededError:
        if not pw:
            raise SystemExit("2FA enabled but TG_2FA_PASSWORD is empty.")
        await client.sign_in(password=pw)

    me = await client.get_me()
    print("AUTH_OK:", me.id, getattr(me, "username", None))
    await client.disconnect()

asyncio.run(main())
PY
```

Restart:

```bash
docker compose up -d trader
docker compose logs -f --tail=80 trader
```

---

# 🔐 Where do you get `TG_2FA_PASSWORD`?

It’s **your Telegram 2-Step Verification password** (the one you set in Telegram app).
In Telegram:

* Settings → Privacy & Security → Two-Step Verification (or “2-Step Verification” / “Cloud Password”)

It is **not** something generated by the system.

---

# 🧾 Notes to add in docs (important)

* If Telethon prompts for input inside container → you’ll get `EOFError`. Always use the non-interactive method above.
* Sessions “break again” if `/app/sessions` is not mapped to a persistent host folder/volume.
* Keep these scripts in docs and **never commit secrets**.

---
