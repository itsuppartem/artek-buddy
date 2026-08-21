from __future__ import annotations

import logging
from typing import Any

from artek_buddy.db.shaping import product_run_status

log = logging.getLogger("artek_buddy")

CURSOR_AUTH_ERROR_HINT = "authentication error"
CURSOR_AUTH_RECYCLE_AFTER = 3
CURSOR_INSTANT_FAIL_S = 2.0


def store_error_code(result: Any, run: Any) -> str | None:
    for obj in (result, run):
        if obj is None:
            continue
        store = getattr(obj, "store", None)
        if store is None:
            continue
        if isinstance(store, dict):
            code = store.get("error_code")
        else:
            code = getattr(store, "error_code", None)
        if code:
            return str(code)
    err = getattr(result, "error", None) if result is not None else None
    if err:
        return str(err)
    return None


def describe_cursor_wait(result: Any, run: Any) -> tuple[str, str | None, str | None]:
    """Return mapped status, result text, and persisted error (None if completed)."""
    status_raw = str(getattr(result, "status", "unknown") if result is not None else "unknown")
    text = getattr(result, "result", None) if result is not None else None
    text = text or ""
    mapped = product_run_status(status_raw)
    if mapped == "completed":
        return mapped, text or None, None
    code = store_error_code(result, run)
    run_id = getattr(run, "id", "") if run is not None else ""
    error = code or f"run failed: {run_id}"
    return mapped, text or None, error


def is_auth_error(error: str | None) -> bool:
    return CURSOR_AUTH_ERROR_HINT in (error or "").lower()


def note_auth_failures(
    consecutive: int,
    *,
    status: str,
    error: str | None,
    duration_s: float,
) -> tuple[int, bool]:
    """Count instant auth-error waits. Return (new_count, should_recycle)."""
    if status == "completed":
        return 0, False
    instant = duration_s < CURSOR_INSTANT_FAIL_S
    if status == "failed" and is_auth_error(error) and instant:
        nxt = consecutive + 1
        return nxt, nxt >= CURSOR_AUTH_RECYCLE_AFTER
    return consecutive, False


def log_cursor_wait(
    run_id: str,
    agent_id: str,
    status: str,
    duration_s: float,
    error_code: str | None,
) -> None:
    log.info(
        "cursor wait run_id=%s agent_id=%s status=%s duration_s=%.3f error_code=%s",
        run_id,
        agent_id,
        status,
        duration_s,
        error_code,
    )
