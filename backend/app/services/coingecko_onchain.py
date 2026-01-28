# backend/app/services/coingecko_onchain.py
from __future__ import annotations

import os
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
        # ✅ accept all common env names (your case: COINGECKO_API_KEY)
        self.api_key = (
            api_key
            or os.getenv("COINGECKO_PRO_API_KEY")
            or os.getenv("CG_PRO_API_KEY")
            or os.getenv("COINGECKO_API_KEY")
        )

        self.base_url = base_url or "https://pro-api.coingecko.com/api/v3/onchain"
        self.session = requests.Session()

        # ✅ fail fast (so we never spam 401s again)
        if not self.api_key:
            raise CoinGeckoOnchainError(
                "CoinGecko API key missing. Set one of: COINGECKO_PRO_API_KEY, CG_PRO_API_KEY, COINGECKO_API_KEY"
            )

        self.session.headers.update({"x-cg-pro-api-key": self.api_key})

    def _get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        url = f"{self.base_url}{path}"
        r = self.session.get(url, params=params, timeout=30)
        if r.status_code >= 400:
            raise CoinGeckoOnchainError(f"CoinGecko error {r.status_code}: {r.text}")
        return r.json()

    def pick_best_pool_for_mint(self, mint: str, network: str = "solana") -> BestPool | None:
        data = self._get(f"/networks/{network}/tokens/{mint}/pools")
        pools = data.get("data") or []
        if not pools:
            return None

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
        if limit < 1:
            limit = 1
        if limit > 1000:
            limit = 1000

        params: dict[str, Any] = {
            "aggregate": str(int(aggregate)),
            "limit": int(limit),
            "currency": currency,
            "token": token,
            "include_empty_intervals": "true" if include_empty_intervals else "false",
        }
        if before_timestamp is not None:
            params["before_timestamp"] = int(before_timestamp)

        data = self._get(f"/networks/{network}/pools/{pool_address}/ohlcv/{timeframe}", params=params)
        attrs = (data.get("data") or {}).get("attributes") or {}
        return attrs.get("ohlcv_list") or []
