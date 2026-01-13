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

JUP_BASE_URL = os.getenv("JUP_BASE_URL", "https://lite-api.jup.ag").strip().rstrip("/")
JUP_QUOTE_URL = f"{JUP_BASE_URL}/swap/v1/quote"
JUP_SWAP_URL = f"{JUP_BASE_URL}/swap/v1/swap"

MAX_SEND_RETRIES = int(os.getenv("JUP_MAX_SEND_RETRIES", "3"))


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


_wallet = _load_keypair()
_WALLET_PUBKEY_STR = str(_wallet.pubkey())


def _rpc_call(method: str, params: list, rpc_url: str) -> Dict[str, Any]:
    payload = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params}
    r = requests.post(rpc_url, json=payload, timeout=30)
    if r.status_code != 200:
        raise RuntimeError(f"RPC {method} HTTP {r.status_code}: {r.text[:250]}")
    return r.json()


def _simulate_tx(raw_tx: VersionedTransaction, rpc_url: str) -> Dict[str, Any]:
    encoded_tx = base64.b64encode(bytes(raw_tx)).decode("utf-8")
    jr = _rpc_call(
        "simulateTransaction",
        [encoded_tx, {"sigVerify": False, "encoding": "base64"}],
        rpc_url,
    )
    if "error" in jr:
        raise RuntimeError(f"RPC simulateTransaction error: {jr['error']}")
    return jr.get("result", {}) or {}


def _send_signed_tx(signed_tx: VersionedTransaction, rpc_url: str) -> str:
    encoded_tx = base64.b64encode(bytes(signed_tx)).decode("utf-8")
    jr = _rpc_call(
        "sendTransaction",
        [
            encoded_tx,
            {
                "skipPreflight": False,
                "preflightCommitment": "confirmed",
                "encoding": "base64",
                "maxRetries": 3,
            },
        ],
        rpc_url,
    )
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


def _jup_get_quote(*, input_mint: str, output_mint: str, in_amount_raw: int, slippage_bps: int) -> Dict[str, Any]:
    params = {
        "inputMint": input_mint,
        "outputMint": output_mint,
        "amount": str(int(in_amount_raw)),
        "slippageBps": str(int(slippage_bps)),
    }
    r = requests.get(JUP_QUOTE_URL, params=params, timeout=12)
    if r.status_code != 200:
        raise RuntimeError(f"Jupiter quote error {r.status_code}: {r.text[:250]}")
    return r.json()


def _jup_build_swap_tx(*, quote_response: Dict[str, Any], wrap_and_unwrap_sol: bool) -> VersionedTransaction:
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
    r = requests.post(JUP_SWAP_URL, json=payload, timeout=20)
    if r.status_code != 200:
        raise RuntimeError(f"Jupiter swap error {r.status_code}: {r.text[:250]}")
    data = r.json()
    swap_tx_b64 = data.get("swapTransaction")
    if not swap_tx_b64:
        raise RuntimeError(f"Jupiter swap response missing swapTransaction: {data}")
    tx_bytes = base64.b64decode(swap_tx_b64)
    return VersionedTransaction.from_bytes(tx_bytes)  # UNSIGNED


def jup_swap_exact_in(
    *,
    input_mint: str,
    output_mint: str,
    in_amount_raw: int,
    slippage_bps: int = 200,
    wrap_and_unwrap_sol: bool = True,
    rpc_url: str | None = None,
    private_key: str | None = None,
) -> Tuple[str, Dict[str, Any]]:
    rpc_url = (rpc_url or RPC_URL).strip()
    if not rpc_url:
        raise RuntimeError("SOLANA_RPC_URL is missing")

    global _wallet, _WALLET_PUBKEY_STR
    if private_key:
        _wallet = _load_keypair(private_key)
        _WALLET_PUBKEY_STR = str(_wallet.pubkey())

    _log(
        "START",
        input=input_mint,
        output=output_mint,
        amount=in_amount_raw,
        bps=slippage_bps,
        priorityLevel=os.getenv("JUP_PRIORITY_LEVEL", "veryHigh"),
        maxLamports=os.getenv("JUP_MAX_PRIORITY_FEE_LAMPORTS", "1000000"),
    )

    quote = _jup_get_quote(
        input_mint=input_mint,
        output_mint=output_mint,
        in_amount_raw=in_amount_raw,
        slippage_bps=slippage_bps,
    )

    last_error: Optional[Exception] = None

    for attempt in range(1, MAX_SEND_RETRIES + 1):
        try:
            _log("BUILD_TX", attempt=attempt)
            raw_tx = _jup_build_swap_tx(
                quote_response=quote,
                wrap_and_unwrap_sol=wrap_and_unwrap_sol,
            )

            _log("SIMULATE", attempt=attempt)
            sim = _simulate_tx(raw_tx, rpc_url)
            if sim.get("err") is not None:
                raise RuntimeError(f"Jupiter simulation error: {sim.get('err')}")

            msg_bytes = to_bytes_versioned(raw_tx.message)
            signature = _wallet.sign_message(msg_bytes)
            signed_tx = VersionedTransaction.populate(raw_tx.message, [signature])

            _log("SEND", attempt=attempt)
            sig_str = _send_signed_tx(signed_tx, rpc_url)
            _log("OK", sig=sig_str, attempt=attempt)
            return sig_str, quote

        except Exception as e:
            last_error = e
            _log("FAIL", attempt=attempt, err=str(e)[:500])
            if _is_blockhash_error(str(e)) and attempt < MAX_SEND_RETRIES:
                continue
            break

    raise RuntimeError(f"Jupiter swap failed: {last_error}")

