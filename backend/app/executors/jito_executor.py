# backend/app/executors/jito_executor.py
"""
Jito bundle submission for Solana.
Submits [swap_tx, tip_tx] as a bundle to Jito block engines.
Bundles land in ~400ms vs. 2-5s for normal RPC submission.
"""
from __future__ import annotations

import os
import time
import random
import requests
import base58
from typing import Dict, Any, List, Tuple, Optional

from solders.keypair import Keypair
from solders.pubkey import Pubkey
from solders.transaction import VersionedTransaction
from solders.message import MessageV0, to_bytes_versioned
from solders.system_program import transfer, TransferParams

# Jito tip accounts (pick one randomly per bundle)
JITO_TIP_ACCOUNTS: List[str] = [
    "96gYZGLnJYVFmbjzopPSU6QiEV5fGqZNyN9nmNhvrZU5",
    "HFqU5x63VTqvQss8hp11i4wVV8bD44PvwucfZ2bU7gRe",
    "Cw8CFyM9FkoMi7K7Crf6HNQqf4uEMzpKw6QNghXLvLkY",
    "ADaUMid9yfUytqMBgopwjb2DTLSokTSzL1zt6iGPaS49",
    "DfXygSm4jCyNCybVYYK6DwvWqjKee8pbDmJGcLWNDXjh",
    "ADuUkR4vqLUMWXxW9gh6D6L8pMSawimctcNZ5pGwDcEt",
    "DttWaMuVvTiduZRnguLF7jNxTgiMBZ1hyAumKUiL2KRL",
    "3AVi9Tg9Uo68tJfuvoKvqKNWKkC5wPdSSdeBnizKZ6jT",
]

# Multiple regions — pick randomly for lowest latency
JITO_BLOCK_ENGINE_URLS: List[str] = [
    "https://mainnet.block-engine.jito.labs.io",
    "https://ny.mainnet.block-engine.jito.labs.io",
    "https://amsterdam.mainnet.block-engine.jito.labs.io",
    "https://frankfurt.mainnet.block-engine.jito.labs.io",
    "https://tokyo.mainnet.block-engine.jito.labs.io",
]

# 0.001 SOL default tip — enough to be competitive without overpaying
JITO_TIP_LAMPORTS = int(os.getenv("JITO_TIP_LAMPORTS", "1000000"))
JITO_TIMEOUT_SEC = float(os.getenv("JITO_TIMEOUT_SEC", "5.0"))


def _log(event: str, **fields) -> None:
    parts = " ".join([f"{k}={v}" for k, v in fields.items()])
    print(f"[JITO_EXEC][{event}] {parts}", flush=True)


def _build_tip_tx(wallet: Keypair, tip_lamports: int, recent_blockhash) -> VersionedTransaction:
    """Build a SOL transfer to a random Jito tip account using the same blockhash as the swap."""
    tip_pubkey = Pubkey.from_string(random.choice(JITO_TIP_ACCOUNTS))
    ix = transfer(TransferParams(
        from_pubkey=wallet.pubkey(),
        to_pubkey=tip_pubkey,
        lamports=tip_lamports,
    ))
    msg = MessageV0.try_compile(
        payer=wallet.pubkey(),
        instructions=[ix],
        address_lookup_table_accounts=[],
        recent_blockhash=recent_blockhash,
    )
    return VersionedTransaction(msg, [wallet])


def _submit_bundle(signed_txs: List[VersionedTransaction], timeout_sec: float = 5.0) -> str:
    """Submit a bundle to a random Jito block engine. Returns bundle UUID."""
    # base58-encode each signed transaction
    encoded = [base58.b58encode(bytes(tx)).decode() for tx in signed_txs]
    url = random.choice(JITO_BLOCK_ENGINE_URLS) + "/api/v1/bundles"
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "sendBundle",
        "params": [encoded],
    }
    r = requests.post(url, json=payload, timeout=timeout_sec)
    if r.status_code != 200:
        raise RuntimeError(f"Jito HTTP {r.status_code}: {r.text[:300]}")
    jr = r.json()
    if "error" in jr:
        raise RuntimeError(f"Jito bundle error: {jr['error']}")
    bundle_id = jr.get("result")
    if not bundle_id:
        raise RuntimeError(f"Jito unexpected response: {jr}")
    return str(bundle_id)


def confirm_bundle(bundle_id: str, timeout_sec: float = 8.0) -> Optional[str]:
    """
    Poll getBundleStatuses until the bundle is confirmed, failed, or timeout.

    Returns:
      "confirmed" | "finalized" — bundle landed successfully
      "failed"                  — bundle was included but TX reverted on-chain
      None                      — timeout or bundle was dropped by the engine
    """
    deadline = time.time() + timeout_sec
    # Prefer a fixed engine for status polling to avoid cross-region inconsistency
    url = JITO_BLOCK_ENGINE_URLS[0] + "/api/v1/bundles"
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "getBundleStatuses",
        "params": [[bundle_id]],
    }

    while time.time() < deadline:
        try:
            r = requests.post(url, json=payload, timeout=2.0)
            if r.status_code == 200:
                jr = r.json()
                values = (jr.get("result") or {}).get("value") or []
                item = values[0] if values else None
                if item is not None:
                    err = item.get("err")
                    if err:
                        _log("BUNDLE_FAILED", bundle_id=bundle_id, err=str(err)[:200])
                        return "failed"
                    status = item.get("confirmationStatus")
                    if status in ("confirmed", "finalized"):
                        _log("BUNDLE_CONFIRMED", bundle_id=bundle_id, status=status)
                        return status
                    # "processed" — still propagating, keep polling
        except Exception:
            pass
        time.sleep(0.35)

    _log("BUNDLE_TIMEOUT", bundle_id=bundle_id, timeout_sec=timeout_sec)
    return None  # dropped or not seen within window


def jup_swap_jito(
    *,
    input_mint: str,
    output_mint: str,
    in_amount_raw: int,
    slippage_bps: int = 200,
    wrap_and_unwrap_sol: bool = True,
    private_key: str | None = None,
    tip_lamports: int | None = None,
) -> Tuple[str, Dict[str, Any]]:
    """
    Get a Jupiter quote, build the swap TX, attach a Jito tip TX,
    and submit both as a Jito bundle.

    Returns (bundle_id, quote_response).
    Bundle lands in ~400ms when validators are running Jito-Solana client.
    """
    # Import here to avoid circular imports at module level
    import app.executors.jup_executor as jup_mod

    jup_mod._ensure_wallet(private_key)
    wallet = jup_mod._wallet
    assert wallet is not None, "Wallet not loaded"

    tip = tip_lamports if tip_lamports is not None else JITO_TIP_LAMPORTS

    _log(
        "START",
        input=input_mint,
        output=output_mint,
        amount=in_amount_raw,
        bps=slippage_bps,
        tip_lamports=tip,
    )

    # 1) Get Jupiter quote
    quote = jup_mod._jup_get_quote(
        input_mint=input_mint,
        output_mint=output_mint,
        in_amount_raw=in_amount_raw,
        slippage_bps=slippage_bps,
        timeout_sec=jup_mod.JUP_QUOTE_TIMEOUT_SEC,
    )

    # 2) Build unsigned swap TX from Jupiter
    _log("BUILD_TX")
    raw_swap_tx = jup_mod._jup_build_swap_tx(
        quote_response=quote,
        wrap_and_unwrap_sol=wrap_and_unwrap_sol,
        timeout_sec=jup_mod.JUP_BUILD_TIMEOUT_SEC,
    )

    # 3) Sign the swap TX
    msg_bytes = to_bytes_versioned(raw_swap_tx.message)
    sig = wallet.sign_message(msg_bytes)
    signed_swap_tx = VersionedTransaction.populate(raw_swap_tx.message, [sig])

    # 4) Build tip TX with the SAME blockhash (required for bundle atomicity)
    recent_blockhash = raw_swap_tx.message.recent_blockhash
    tip_tx = _build_tip_tx(wallet, tip, recent_blockhash)

    # 5) Submit bundle [swap, tip]
    _log("SUBMIT_BUNDLE", tip_lamports=tip)
    bundle_id = _submit_bundle([signed_swap_tx, tip_tx], timeout_sec=JITO_TIMEOUT_SEC)
    _log("OK", bundle_id=bundle_id)

    return bundle_id, quote
