from __future__ import annotations
import requests
from typing import Optional

DEX_TOKEN_URL = "https://api.dexscreener.com/latest/dex/tokens/"
SOL_CHAIN_ID = "solana"

def fetch_price_usd(mint: str, timeout: int = 10) -> Optional[float]:
    try:
        r = requests.get(f"{DEX_TOKEN_URL}{mint}", timeout=timeout)
        if r.status_code != 200:
            return None
        j = r.json()
        pairs = j.get("pairs") or []
        if not pairs:
            return None

        chosen = None
        for p in pairs:
            if p.get("chainId") == SOL_CHAIN_ID:
                chosen = p
                break
        if not chosen:
            chosen = pairs[0]

        price_raw = chosen.get("priceUsd")
        if price_raw is None:
            return None
        price = float(price_raw)
        if price <= 0:
            return None
        return price
    except Exception:
        return None
