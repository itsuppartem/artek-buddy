from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from typing import Any

from artek_buddy.observe import redact_text

# Bound for a single-host Postgres volume. Product rows stay queryable;
# a cursor older than the retained window gets an explicit resync/gap.
DEFAULT_ACTIVITY_RETENTION = 10000
ACTIVITY_REPLAY_LIMIT = 500

_FORBIDDEN_ACTIVITY_KEYS = {
    "token",
    "token_hash",
    "secret",
    "secret_hash",
    "password",
    "key",
    "tool_args",
    "screenshot",
    "image_base64",
    "image_png_base64",
}


def sanitize_activity_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Drop secrets, raw tool args, and screenshots from an activity payload."""
    sanitized: dict[str, Any] = {}
    for key, value in payload.items():
        if key.lower() in _FORBIDDEN_ACTIVITY_KEYS:
            continue
        if isinstance(value, str):
            sanitized[key] = redact_text(value)
        elif isinstance(value, dict):
            sanitized[key] = sanitize_activity_payload(value)
        elif isinstance(value, list):
            sanitized[key] = [
                sanitize_activity_payload(item)
                if isinstance(item, dict)
                else (redact_text(item) if isinstance(item, str) else item)
                for item in value
            ]
        else:
            sanitized[key] = value
    return sanitized


def parse_activity_cursor(
    after: str | None,
    last_event_id: str | None,
    after_sequence: int | None,
) -> int | None:
    """Prefer an explicit sequence, then a numeric Last-Event-ID / after id."""
    if after_sequence is not None:
        return after_sequence
    for raw in (after, last_event_id):
        if raw is None:
            continue
        try:
            return int(raw)
        except ValueError:
            continue
    return None


@dataclass
class ActivityRecord:
    seq: int
    id: str
    event_type: str
    event_version: int
    actor: str
    device_id: str | None
    resource: str
    payload: dict[str, Any]
    created_at: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_sse(self) -> str:
        data = json.dumps(self.to_dict(), ensure_ascii=False)
        return f"id: {self.seq}\nevent: {self.event_type}\ndata: {data}\n\n"
