"""
Seed channels into the app via API.

Edit the CHANNELS list below with your own channel keys and Telegram usernames,
then run once:

    python scripts/seed_channels.py

Where to find good Solana signal channels:
  - Browse GMGN.ai charts → look at recent top performers → check if the caller
    has a public Telegram channel linked in their profile.
  - Search Telegram for "solana calls", "solana gems", "memecoin alpha", etc.
  - Community lists on X / Twitter (search #solanacalls or #memecoinalpha).

Tip: start with 2–3 channels and evaluate their hit-rate from the dashboard
before adding more. Quality over quantity.
"""
import requests

API = "http://localhost:8000"

# Replace these with your own channels.
# Format: ("short_key", "telegram_username_without_@")
CHANNELS = [
    # ("example_key", "example_channel_username"),
]

if not CHANNELS:
    print("No channels configured. Edit the CHANNELS list in this file first.")
    raise SystemExit(0)

for key, username in CHANNELS:
    r = requests.post(f"{API}/channels", json={
        "key": key,
        "telegram_username": username,
        "enabled": True,
        "live_enabled": False,
    })
    if r.status_code == 200:
        print(f"✅ added {username}")
    elif r.status_code == 409:
        print(f"⏭  {username} already exists")
    else:
        print(f"❌ {username} — {r.status_code} {r.text[:100]}")

print("Done.")
