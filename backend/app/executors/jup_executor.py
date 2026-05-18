# backend/app/executors/jup_executor.py
from __future__ import annotations

import os
import json
import base64
from typing import Any, Optional, Tuple, Dict

import requests
import base58

from solders.keypair import Keypair
from solders.transaction import VersionedTransaction
from solders.message import to_bytes_versioned

SOL_MINT = "So11111111111111111111111111111111111111112"

RPC_URL = os.getenv("SOLANA_RPC_URL", "https://api.mainnet-beta.solana.com").strip()

JUP_BASE_URL = os.getenv("JUP_BASE_URL", "https://api.jup.ag").strip().rstrip("/")

# Ultra API (primary — single call, no RPS cap, free)
JUP_ULTRA_ORDER_URL = f"{JUP_BASE_URL}/ultra/v1/order"

# Legacy swap endpoints (kept as internal fallback)
JUP_QUOTE_URL = f"{JUP_BASE_URL}/swap/v1/quote"
JUP_SWAP_URL = f"{JUP_BASE_URL}/swap/v1/swap"

JUP_API_KEY = os.getenv("JUP_API_KEY", "").strip()
_JUP_HEADERS = {"Authorization": f"Bearer {JUP_API_KEY}"} if JUP_API_KEY else {}

# Ultra timeout — /order is a single round-trip (~200-500ms normally)
JUP_ULTRA_TIMEOUT_SEC = float(os.getenv("JUP_ULTRA_TIMEOUT_SEC", "8.0"))

MAX_SEND_RETRIES = int(os.getenv("JUP_MAX_SEND_RETRIES", "3"))

# Aggressive knobs (used by workers too)
LIVE_FAST_MODE = os.getenv("LIVE_FAST_MODE", "1").strip() not in ("0", "false", "False")
# Jupiter API (quote + build) takes 1-3s — enforce a safe minimum of 5s.
# LIVE_HTTP_TIMEOUT_SEC kept for backwards compatibility but clamped.
LIVE_HTTP_TIMEOUT_SEC = max(float(os.getenv("LIVE_HTTP_TIMEOUT_SEC", "5.0")), 5.0)
JUP_QUOTE_TIMEOUT_SEC = float(os.getenv("JUP_QUOTE_TIMEOUT_SEC", str(LIVE_HTTP_TIMEOUT_SEC)))
JUP_BUILD_TIMEOUT_SEC = float(os.getenv("JUP_BUILD_TIMEOUT_SEC", str(max(LIVE_HTTP_TIMEOUT_SEC, 8.0))))


def _log(event: str, **fields) -> None:
    parts = " ".join([f"{k}={v}" for k, v in fields.items()])
    print(f"[JUP_EXEC][{event}] {parts}", flush=True)


def sol_to_lamports(sol: float) -> int:
    return int(sol * 1_000_000_000)


def _load_keypair(private_key: str | None = None) -> Keypair:
    raw = (private_key or os.getenv("SOLANA_PRIVATE_KEY") or "").strip()
    if not raw:
        raise ValueError("SOLANA_PRIVATE_KEY not set (or private_key arg missing).")

    # JSON array format
    try:
        data = json.loads(raw)
        if isinstance(data, list) and all(isinstance(x, int) for x in data):
            return Keypair.from_bytes(bytes(data))
    except json.JSONDecodeError:
        pass

    # base58 secret key
    try:
        secret = base58.b58decode(raw)
        return Keypair.from_bytes(secret)
    except Exception as e:
        raise ValueError(f"Invalid SOLANA_PRIVATE_KEY format: {e}")


# Lazy-loaded at first swap call — avoids crashing containers that don't use Solana keys
_wallet: Keypair | None = None
_WALLET_PUBKEY_STR: str = ""


def _ensure_wallet(private_key: str | None = None) -> None:
    global _wallet, _WALLET_PUBKEY_STR
    if private_key:
        _wallet = _load_keypair(private_key)
        _WALLET_PUBKEY_STR = str(_wallet.pubkey())
    elif _wallet is None:
        _wallet = _load_keypair()
        _WALLET_PUBKEY_STR = str(_wallet.pubkey())


def _rpc_call(method: str, params: list, rpc_url: str, timeout_sec: float = 30.0) -> Dict[str, Any]:
    payload = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params}
    r = requests.post(rpc_url, json=payload, timeout=timeout_sec)
    if r.status_code != 200:
        raise RuntimeError(f"RPC {method} HTTP {r.status_code}: {r.text[:250]}")
    return r.json()


def _send_signed_tx(signed_tx: VersionedTransaction, rpc_url: str, *, fast_mode: bool) -> str:
    """
    Aggressive:
      - skipPreflight=True
      - preflightCommitment='processed'
      - maxRetries=0
    """
    encoded_tx = base64.b64encode(bytes(signed_tx)).decode("utf-8")

    opts = {
        "skipPreflight": bool(fast_mode),
        "preflightCommitment": "processed" if fast_mode else "confirmed",
        "encoding": "base64",
        "maxRetries": 0 if fast_mode else 3,
    }

    jr = _rpc_call("sendTransaction", [encoded_tx, opts], rpc_url, timeout_sec=8.0 if fast_mode else 30.0)
    if "error" in jr:
        raise RuntimeError(f"RPC sendTransaction error: {jr['error']}")
    sig = jr.get("result")
    if not sig:
        raise RuntimeError(f"RPC sendTransaction unexpected response: {jr}")
    return str(sig)


def _is_blockhash_error(msg: str) -> bool:
    m = msg.lower()
    return any(
        p in m
        for p in [
            "blockhashnotfound",
            "blockhash not found",
            "expired blockhash",
            "this transaction has expired",
        ]
    )


def _jup_get_quote(
    *,
    input_mint: str,
    output_mint: str,
    in_amount_raw: int,
    slippage_bps: int,
    timeout_sec: float,
) -> Dict[str, Any]:
    params = {
        "inputMint": input_mint,
        "outputMint": output_mint,
        "amount": str(int(in_amount_raw)),
        "slippageBps": str(int(slippage_bps)),
    }
    r = requests.get(JUP_QUOTE_URL, params=params, headers=_JUP_HEADERS, timeout=timeout_sec)
    if r.status_code != 200:
        raise RuntimeError(f"Jupiter quote error {r.status_code}: {r.text[:250]}")
    return r.json()


def _jup_build_swap_tx(
    *,
    quote_response: Dict[str, Any],
    wrap_and_unwrap_sol: bool,
    timeout_sec: float,
) -> VersionedTransaction:
    payload = {
        "quoteResponse": quote_response,
        "userPublicKey": _WALLET_PUBKEY_STR,
        "wrapAndUnwrapSol": bool(wrap_and_unwrap_sol),
        "dynamicComputeUnitLimit": True,
        "dynamicSlippage": False,
        "prioritizationFeeLamports": {
            "priorityLevelWithMaxLamports": {
                "maxLamports": int(os.getenv("JUP_MAX_PRIORITY_FEE_LAMPORTS", "1000000")),
                "priorityLevel": os.getenv("JUP_PRIORITY_LEVEL", "veryHigh"),
            }
        },
    }
    r = requests.post(JUP_SWAP_URL, json=payload, headers=_JUP_HEADERS, timeout=timeout_sec)
    if r.status_code != 200:
        raise RuntimeError(f"Jupiter swap error {r.status_code}: {r.text[:250]}")
    data = r.json()
    swap_tx_b64 = data.get("swapTransaction")
    if not swap_tx_b64:
        raise RuntimeError(f"Jupiter swap response missing swapTransaction: {data}")
    tx_bytes = base64.b64decode(swap_tx_b64)
    return VersionedTransaction.from_bytes(tx_bytes)  # UNSIGNED


def _ultra_get_order(
    *,
    input_mint: str,
    output_mint: str,
    in_amount_raw: int,
    slippage_bps: int,
    timeout_sec: float,
) -> tuple[VersionedTransaction, str]:
    """
    Call Ultra /order endpoint. Single API call — replaces _jup_get_quote + _jup_build_swap_tx.
    Returns (unsigned_tx, request_id). No RPS cap on Ultra plan.
    """
    payload = {
        "inputMint": input_mint,
        "outputMint": output_mint,
        "amount": int(in_amount_raw),
        "taker": _WALLET_PUBKEY_STR,
        "slippageBps": int(slippage_bps),
    }
    r = requests.post(JUP_ULTRA_ORDER_URL, json=payload, headers=_JUP_HEADERS, timeout=timeout_sec)
    if r.status_code != 200:
        raise RuntimeError(f"Jupiter Ultra order error {r.status_code}: {r.text[:250]}")
    data = r.json()
    tx_b64 = data.get("transaction")
    request_id = data.get("requestId") or ""
    if not tx_b64:
        raise RuntimeError(f"Jupiter Ultra order missing transaction: {data}")
    return VersionedTransaction.from_bytes(base64.b64decode(tx_b64)), request_id


def jup_swap_exact_in(
    *,
    input_mint: str,
    output_mint: str,
    in_amount_raw: int,
    slippage_bps: int = 200,
    wrap_and_unwrap_sol: bool = True,
    rpc_url: str | None = None,
    private_key: str | None = None,
    fast_mode: bool | None = None,
) -> Tuple[str, Dict[str, Any]]:
    rpc_url = (rpc_url or RPC_URL).strip()
    if not rpc_url:
        raise RuntimeError("SOLANA_RPC_URL is missing")

    fast = LIVE_FAST_MODE if fast_mode is None else bool(fast_mode)
    quote_timeout = JUP_QUOTE_TIMEOUT_SEC if fast else 12.0
    build_timeout = JUP_BUILD_TIMEOUT_SEC if fast else 20.0

    _ensure_wallet(private_key)

    _log("ULTRA_START", input=input_mint[:8], output=output_mint[:8], amount=in_amount_raw, bps=slippage_bps, fast=fast)

    last_error: Optional[Exception] = None

    for attempt in range(1, MAX_SEND_RETRIES + 1):
        try:
            # Single Ultra API call — replaces quote + build (no RPS limit)
            _log("ULTRA_ORDER", attempt=attempt)
            raw_tx, _ = _ultra_get_order(
                input_mint=input_mint,
                output_mint=output_mint,
                in_amount_raw=in_amount_raw,
                slippage_bps=slippage_bps,
                timeout_sec=JUP_ULTRA_TIMEOUT_SEC,
            )

            assert _wallet is not None, "Wallet not loaded"
            msg_bytes = to_bytes_versioned(raw_tx.message)
            signature = _wallet.sign_message(msg_bytes)
            signed_tx = VersionedTransaction.populate(raw_tx.message, [signature])

            _log("ULTRA_SEND", attempt=attempt, fast=fast)
            sig_str = _send_signed_tx(signed_tx, rpc_url, fast_mode=fast)
            _log("ULTRA_OK", sig=sig_str, attempt=attempt)
            return sig_str, {}

        except Exception as e:
            last_error = e
            _log("ULTRA_FAIL", attempt=attempt, err=str(e)[:500])
            if _is_blockhash_error(str(e)) and attempt < MAX_SEND_RETRIES:
                continue  # fresh _ultra_get_order on next attempt = fresh blockhash
            break

    raise RuntimeError(f"Jupiter Ultra swap failed: {last_error}")
