from __future__ import annotations
import re

BASE58_ALPHABET = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
CA_REGEX = re.compile(rf"(?<![{BASE58_ALPHABET}])([{BASE58_ALPHABET}]{{32,44}})(?:pump)?(?![{BASE58_ALPHABET}])")

def extract_first_solana_ca(text: str) -> str | None:
    if not text:
        return None
    m = CA_REGEX.search(text)
    if not m:
        return None
    return m.group(1)
