from __future__ import annotations

import hashlib
import secrets

PAIRING_TTL_SECONDS = 15 * 60
PAIRING_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def hash_secret(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def host_token_match(provided: str, expected: str) -> bool:
    if not provided or not expected:
        return False
    if len(provided) != len(expected):
        return False
    return secrets.compare_digest(provided, expected)


def new_device_token() -> str:
    return "dev_" + secrets.token_urlsafe(32)


def new_pairing_code() -> str:
    raw = "".join(secrets.choice(PAIRING_ALPHABET) for _ in range(8))
    return f"{raw[:4]}-{raw[4:]}"


def normalize_pairing_code(code: str) -> str:
    return "".join(ch for ch in code.upper() if ch.isalnum())
