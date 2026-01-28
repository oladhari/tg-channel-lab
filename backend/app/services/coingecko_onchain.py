# backend/app/services/coingecko_onchain.py
from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Any

import requests


@dataclass(frozen=True)
class BestPool:
    dex_id: str
    pool_address: str


class CoinGeckoOnchainError(RuntimeError):
    pass


class CoinGeckoOnchainClient:
    def __init__(self, api_key: str | None = None, base_url: str | None = None):
        self.api_key = api_key or os.getenv("COINGECKO_PRO_API_KEY") or os.getenv("CG_PRO_API_KEY")
        self.base_url = base_url or "https://pro-api.coingecko.com/api/v3/onchain"
        self.session = requests.Session()
        self.session.headers.update({"x-cg-pro-api-key": self.api_key or ""})

    def _get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        url = f"{self.base_url}{path}"
        r = self.session.get(url, params=params, timeout=30)
        if r.status_code >= 400:
            raise CoinGeckoOnchainError(f"CoinGecko error {r.status_code}: {r.text}")
        return r.json()

    def pick_best_pool_for_mint(self, mint: str, network: str = "solana") -> BestPool | None:
        # your existing logic can stay — this is just placeholder signature.
        # must return BestPool(dex_id=..., pool_address=...)
        data = self._get(f"/networks/{network}/tokens/{mint}/pools")
        pools = data.get("data") or []
        if not pools:
            return None

        # Pick highest liquidity/reserve_in_usd when available
        best = None
        best_liq = -1.0
        for p in pools:
            try:
                attrs = p.get("attributes") or {}
                liq = float(attrs.get("reserve_in_usd") or 0.0)
                dex = (p.get("relationships", {}).get("dex", {}).get("data", {}) or {}).get("id") or "unknown"
                addr = attrs.get("address") or p.get("id", "").split("_")[-1]
                if liq > best_liq and addr:
                    best_liq = liq
                    best = BestPool(dex_id=str(dex), pool_address=str(addr))
            except Exception:
                continue

        return best

    def fetch_ohlcv(
        self,
        pool_address: str,
        timeframe: str,
        *,
        network: str = "solana",
        aggregate: int = 1,
        before_timestamp: int | None = None,
        limit: int = 100,
        currency: str = "usd",
        token: str = "base",
        include_empty_intervals: bool = True,
    ) -> list[list[float]]:
        # Hard safety:
        if limit < 1:
            limit = 1
        if limit > 1000:
            limit = 1000

        params: dict[str, Any] = {
            "aggregate": str(int(aggregate)),
            "limit": int(limit),
            "currency": currency,
            "token": token,
            # CoinGecko requires lowercase true/false strings
            "include_empty_intervals": "true" if include_empty_intervals else "false",
        }
        if before_timestamp is not None:
            params["before_timestamp"] = int(before_timestamp)

        data = self._get(f"/networks/{network}/pools/{pool_address}/ohlcv/{timeframe}", params=params)
        attrs = (data.get("data") or {}).get("attributes") or {}
        return attrs.get("ohlcv_list") or []
