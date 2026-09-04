from __future__ import annotations

import hashlib
import secrets
import time

PAIRING_TTL_SECONDS = 15 * 60
PAIRING_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
PAIRING_ATTEMPT_LIMIT = 8
PAIRING_ATTEMPT_WINDOW_SECONDS = 5 * 60


class AttemptLimiter:
    """In-memory sliding window for pairing guesses from one client."""

    def __init__(self, *, limit: int, window_seconds: float) -> None:
        self.limit = limit
        self.window_seconds = window_seconds
        self._hits: dict[str, list[float]] = {}

    def _prune(self, key: str, now: float) -> list[float]:
        hits = [stamp for stamp in self._hits.get(key, []) if now - stamp < self.window_seconds]
        if hits:
            self._hits[key] = hits
        else:
            self._hits.pop(key, None)
        return hits

    def allow(self, key: str, now: float | None = None) -> bool:
        current = time.monotonic() if now is None else now
        return len(self._prune(key, current)) < self.limit

    def record(self, key: str, now: float | None = None) -> None:
        current = time.monotonic() if now is None else now
        hits = self._prune(key, current)
        hits.append(current)
        self._hits[key] = hits


pairing_attempts = AttemptLimiter(
    limit=PAIRING_ATTEMPT_LIMIT,
    window_seconds=PAIRING_ATTEMPT_WINDOW_SECONDS,
)


def hash_secret(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def derive_supervisor_token(host_token: str) -> str:
    """Supervisor bearer when SANDBOX_SUPERVISOR_TOKEN is unset.

    The host token itself must not authenticate to :7091. A leaked supervisor
    token also cannot be reversed back into AGENT_HTTP_TOKEN.
    """
    return hashlib.sha256(f"supervisor:{host_token}".encode()).hexdigest()


def supervisor_token(host_token: str, explicit: str = "") -> str:
    token = (explicit or "").strip()
    if token:
        return token
    return derive_supervisor_token(host_token)


def derive_credential_broker_token(host_token: str) -> str:
    """Domain-separated bearer for the loopback credential broker."""
    return hashlib.sha256(f"credential-broker:{host_token}".encode()).hexdigest()


def credential_broker_token(host_token: str, explicit: str = "") -> str:
    token = (explicit or "").strip()
    if token:
        return token
    return derive_credential_broker_token(host_token)


def derive_credential_executor_token(host_token: str) -> str:
    """Internal executor bearer; not valid for the storage broker."""
    return hashlib.sha256(f"credential-executor:{host_token}".encode()).hexdigest()


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
