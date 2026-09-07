from __future__ import annotations

import json
import logging
import secrets
from dataclasses import asdict, dataclass
from typing import Any, Literal

from artek_buddy.observe import redact_text

log = logging.getLogger("artek_buddy.jobs")

JobState = Literal["queued", "running", "succeeded", "failed", "cancelled", "dead"]

_FORBIDDEN_PAYLOAD_KEYS = {
    "token",
    "token_hash",
    "secret",
    "secret_hash",
    "password",
    "key",
}


def calculate_backoff_seconds(
    attempts: int,
    base: float = 10.0,
    max_backoff: float = 300.0,
    jitter: bool = True,
) -> float:
    """Compute exponential backoff with jitter in seconds."""
    multiplier = 2 ** max(0, attempts - 1)
    raw = min(max_backoff, base * multiplier)
    if jitter:
        # 15% random jitter
        factor = secrets.SystemRandom().uniform(0.85, 1.15)
        raw = raw * factor
    return round(max(1.0, raw), 2)


def sanitize_job_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Scrub sensitive secrets from job payloads before export/listing."""
    sanitized: dict[str, Any] = {}
    for k, v in payload.items():
        if k.lower() in _FORBIDDEN_PAYLOAD_KEYS:
            continue
        if isinstance(v, str):
            sanitized[k] = redact_text(v)
        elif isinstance(v, dict):
            sanitized[k] = sanitize_job_payload(v)
        else:
            sanitized[k] = v
    return sanitized


@dataclass
class JobRecord:
    id: str
    job_type: str
    resource_id: str | None
    idempotency_key: str | None
    state: JobState
    payload: dict[str, Any]
    result: dict[str, Any] | None
    last_error: str | None
    attempts: int
    max_attempts: int
    lease_owner: str | None
    lease_expires_at: str | None
    run_at: str
    created_at: str
    updated_at: str
    completed_at: str | None = None

    def to_dict(self, redact: bool = True) -> dict[str, Any]:
        data = asdict(self)
        if redact:
            data["payload"] = sanitize_job_payload(self.payload)
            if self.last_error:
                data["last_error"] = redact_text(self.last_error)
        return data
