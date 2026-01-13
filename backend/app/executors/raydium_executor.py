# backend/app/executors/raydium_executor.py
from __future__ import annotations

import os
import json
import base64
import time
from typing import Optional, Tuple, List, Any

import requests
import base58

from solana.rpc.api import Client as SolClient
from solana.rpc.types import TokenAccountOpts

from solders.keypair import Keypair
from solders.pubkey import Pubkey
from solders.transaction import VersionedTransaction

WSOL_MINT = "So11111111111111111111111111111111111111112"

TOKEN_PROGRAM_ID = Pubkey.from_string("TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA")
TOKEN_2022_PROGRAM_ID = Pubkey.from_string("TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb")


def _load_keypair(private_key: str | None = None) -> Keypair:
    raw = (private_key or os.environ.get("SOLANA_PRIVATE_KEY") or "").strip()
    if not raw:
        raise RuntimeError("SOLANA_PRIVATE_KEY env var not set")

    try:
        parsed = json.loads(raw)
        if isinstance(parsed, list):
            return Keypair.from_bytes(bytes(parsed))
    except Exception:
        pass

    secret_bytes = base58.b58decode(raw)
    return Keypair.from_bytes(secret_bytes)


def _rpc_client(rpc_url: str | None = None) -> SolClient:
    url = (rpc_url or os.getenv("SOLANA_RPC_URL", "https://api.mainnet-beta.solana.com")).strip()
    return SolClient(url)


def _swap_host() -> str:
    return os.getenv("RAYDIUM_SWAP_HOST", "https://transaction-v1.raydium.io").strip().rstrip("/")


def _tx_version() -> str:
    return os.getenv("RAYDIUM_TX_VERSION", "V0").strip().upper()


def _cu_price_micro_lamports() -> str:
    return str(os.getenv("RAYDIUM_CU_PRICE_MICRO_LAMPORTS", "0")).strip()


def _get_ata(owner: Pubkey, mint: Pubkey) -> Pubkey:
    ATA_PROGRAM = Pubkey.from_string("ATokenGPvbdGVxr1b2hvZbsiqW5xWH25efTNsLJA8knL")
    seeds = [bytes(owner), bytes(TOKEN_PROGRAM_ID), bytes(mint)]
    ata, _bump = Pubkey.find_program_address(seeds, ATA_PROGRAM)
    return ata


def get_token_balance_raw(token_mint: str, retries: int = 2, delay_sec: float = 0.35) -> int:
    client = _rpc_client()
    kp = _load_keypair()
    owner = kp.pubkey()
    mint_pk = Pubkey.from_string(token_mint)

    last_err = None
    for _ in range(retries + 1):
        try:
            total = 0

            resp1 = client.get_token_accounts_by_owner(
                owner,
                opts=TokenAccountOpts(mint=mint_pk),
                program_id=TOKEN_PROGRAM_ID,
            )
            resp2 = client.get_token_accounts_by_owner(
                owner,
                opts=TokenAccountOpts(mint=mint_pk),
                program_id=TOKEN_2022_PROGRAM_ID,
            )

            def _sum_from_resp(resp) -> int:
                if not isinstance(resp, dict):
                    resp = resp.to_json() if hasattr(resp, "to_json") else resp.__dict__
                vals = resp.get("result", {}).get("value", []) if isinstance(resp, dict) else []
                s = 0
                for item in vals:
                    try:
                        parsed = item["account"]["data"]["parsed"]
                        amt = parsed["info"]["tokenAmount"]["amount"]
                        s += int(amt)
                    except Exception:
                        continue
                return s

            total += _sum_from_resp(resp1)
            total += _sum_from_resp(resp2)
            return int(total)

        except Exception as e:
            last_err = e
            time.sleep(delay_sec)

    raise RuntimeError(f"get_token_balance_raw failed: {last_err}")


def raydium_compute_swap_base_in(
    input_mint: str,
    output_mint: str,
    amount_raw: int,
    slippage_bps: int,
    tx_version: Optional[str] = None,
    timeout: int = 10,
) -> dict:
    host = _swap_host()
    txv = (tx_version or _tx_version()).upper()

    url = f"{host}/compute/swap-base-in"
    params = {
        "inputMint": input_mint,
        "outputMint": output_mint,
        "amount": str(int(amount_raw)),
        "slippageBps": str(int(slippage_bps)),
        "txVersion": txv,
    }

    r = requests.get(url, params=params, timeout=timeout)
    r.raise_for_status()
    data = r.json()
    if not data.get("success", False):
        raise RuntimeError(f"Raydium compute failed: {data}")
    return data


def raydium_build_swap_txs(
    swap_response: dict,
    wallet_pubkey: str,
    input_account: Optional[str],
    output_account: Optional[str],
    wrap_sol: bool,
    unwrap_sol: bool,
    tx_version: Optional[str] = None,
    cu_price_micro_lamports: Optional[str] = None,
    timeout: int = 10,
) -> List[str]:
    host = _swap_host()
    txv = (tx_version or _tx_version()).upper()
    cu_price = (cu_price_micro_lamports or _cu_price_micro_lamports()).strip()

    url = f"{host}/transaction/swap-base-in"
    body: dict[str, Any] = {
        "txVersion": txv,
        "swapResponse": swap_response,
        "wallet": wallet_pubkey,
        "wrapSol": bool(wrap_sol),
        "unwrapSol": bool(unwrap_sol),
        "computeUnitPriceMicroLamports": str(cu_price),
    }

    if not wrap_sol:
        if not input_account:
            raise RuntimeError("input_account required when wrapSol=False")
        body["inputAccount"] = input_account

    if output_account:
        body["outputAccount"] = output_account

    r = requests.post(url, json=body, timeout=timeout)
    r.raise_for_status()
    data = r.json()
    if not data.get("success", False):
        raise RuntimeError(f"Raydium tx build failed: {data}")

    txs = data.get("data", [])
    return [x["transaction"] for x in txs if x.get("transaction")]


def _send_v0_txs(base64_txs: List[str], kp: Keypair, rpc_url: str | None = None) -> List[str]:
    client = _rpc_client(rpc_url)
    sigs: List[str] = []

    for tx_b64 in base64_txs:
        raw = base64.b64decode(tx_b64)
        vtx = VersionedTransaction.from_bytes(raw)
        vtx_signed = vtx.sign([kp])

        resp = client.send_raw_transaction(
            bytes(vtx_signed),
            opts={"skip_preflight": True, "max_retries": 3},
        )

        if isinstance(resp, dict):
            sig = resp.get("result")
        else:
            sig = getattr(resp, "value", None) or getattr(resp, "result", None)

        if not sig:
            raise RuntimeError(f"Raydium send tx failed (no signature): {resp}")
        sigs.append(sig)

    return sigs


def raydium_swap_exact_in(
    *,
    input_mint: str,
    output_mint: str,
    in_amount_raw: int,
    slippage_bps: int,
    wrap_and_unwrap_sol: bool = True,
    rpc_url: str | None = None,
    private_key: str | None = None,
) -> Tuple[List[str], dict[str, Any]]:
    """
    WORKING synchronous Raydium swap.
    Returns: ([sig...], compute_response_dict)
    """
    kp = _load_keypair(private_key)
    owner = kp.pubkey()

    txv = _tx_version()
    is_input_sol = (input_mint == WSOL_MINT) and wrap_and_unwrap_sol
    is_output_sol = (output_mint == WSOL_MINT) and wrap_and_unwrap_sol

    input_account = None
    output_account = None

    if not is_input_sol:
        input_account = str(_get_ata(owner, Pubkey.from_string(input_mint)))
    if not is_output_sol:
        output_account = str(_get_ata(owner, Pubkey.from_string(output_mint)))

    compute_resp = raydium_compute_swap_base_in(
        input_mint=input_mint,
        output_mint=output_mint,
        amount_raw=in_amount_raw,
        slippage_bps=slippage_bps,
        tx_version=txv,
    )

    txs_b64 = raydium_build_swap_txs(
        swap_response=compute_resp,
        wallet_pubkey=str(owner),
        input_account=input_account,
        output_account=output_account,
        wrap_sol=is_input_sol,
        unwrap_sol=is_output_sol,
        tx_version=txv,
    )

    sigs = _send_v0_txs(txs_b64, kp, rpc_url)
    return sigs, compute_resp
