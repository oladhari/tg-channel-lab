"""
Add all channels to the app via API.
Run once: python scripts/seed_channels.py
"""
import requests

API = "http://localhost:8000"

CHANNELS = [
    ("bat",                        "bat_gamble"),
    ("matt",                       "mattprintalphacalls"),
    ("seekrtrending",              "seekrtrending"),
    ("memesdontlies",              "memesdontlies"),
    ("insightcasino",              "insightcasino"),
    ("pikachucallsgirls",          "pikachucallsgirls"),
    ("azunasplays",                "azunasplays"),
    ("memecoincallsignal",         "memecoincallsignal"),
    ("zen_call",                   "zen_call"),
    ("minegems",                   "minegems"),
    ("memecoinpumps300x",          "memecoinpumps300x"),
    ("kolsignal",                  "kolsignal"),
    ("deezesignal",                "deezesignal"),
    ("earlybirdtg",                "earlybirdtg"),
    ("michiosuzukiofsatoshicalls", "michiosuzukiofsatoshicalls"),
    ("marksgems",                  "marksgems"),
    ("alphakollswithins",          "alphakollswithins"),
    ("wesendingshit",              "wesendingshit"),
    ("tradersviewtrenches",        "tradersviewtrenches"),
    ("marcellcooks",               "marcellcooks"),
    ("alphakingsol",               "alphakingsol"),
    ("mcdonald100xcalls",          "mcdonald100xcalls"),
    ("cto_scanner",                "cto_scanner"),
    ("michelleshills",             "michelleshills"),
]

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
