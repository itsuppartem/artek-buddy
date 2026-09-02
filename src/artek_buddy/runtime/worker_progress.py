from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from artek_buddy.observe import redact_text

PROGRESS_FLOOR_S = 45.0
STEP_MAX = 200


def clip_step(value: Any) -> str:
    if isinstance(value, list):
        text = ", ".join(str(item).strip() for item in value if str(item).strip())
    else:
        text = str(value or "").strip()
    return redact_text(" ".join(text.split()))[:STEP_MAX]


def format_progress_line(step: str, remaining: str | None = None) -> str:
    current = clip_step(step)
    leftover = clip_step(remaining or "")
    if not current:
        return ""
    if leftover:
        return f"Still working: {current}. Next: {leftover}."
    return f"Still working: {current}."


def posted_unix(value: Any) -> float | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        moment = value if value.tzinfo is not None else value.replace(tzinfo=UTC)
        return moment.timestamp()
    text = str(value).strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(text).timestamp()
    except ValueError:
        return None


def should_post_progress(
    *,
    line: str,
    last_line: str | None,
    last_posted_at: float | None,
    now: float,
    floor_s: float = PROGRESS_FLOOR_S,
) -> bool:
    if not line:
        return False
    if last_line == line:
        return False
    if last_posted_at is None:
        return True
    return (now - last_posted_at) >= floor_s
