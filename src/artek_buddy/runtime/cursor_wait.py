from __future__ import annotations

import logging
from typing import Any

from artek_buddy.db.shaping import TURN_FAILED, owner_visible_error, product_run_status

log = logging.getLogger("artek_buddy")

CURSOR_AUTH_ERROR_HINT = "authentication error"
CURSOR_AUTH_RECYCLE_AFTER = 3
CURSOR_INSTANT_FAIL_S = 2.0
DEAD_WAIT_NEXT_STEP = (
    "The turn failed. The host retried. Send again — the host will start a new session."
)


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
    error = owner_visible_error(code, str(run_id or ""))
    return mapped, text or None, error


def is_auth_error(error: str | None) -> bool:
    return CURSOR_AUTH_ERROR_HINT in (error or "").lower()


def is_dead_wait_error(error: str | None) -> bool:
    text = (error or "").strip().lower()
    return text == TURN_FAILED.lower() or text.startswith("the turn failed")


def note_auth_failures(
    consecutive: int,
    *,
    status: str,
    error: str | None,
    duration_s: float,
) -> tuple[int, bool]:
    """Count instant auth-error waits. Recycle a dead wait (The turn failed, ~0s) immediately."""
    if status == "completed":
        return 0, False
    instant = duration_s < CURSOR_INSTANT_FAIL_S
    if status == "failed" and instant and is_auth_error(error):
        nxt = consecutive + 1
        return nxt, nxt >= CURSOR_AUTH_RECYCLE_AFTER
    if status == "failed" and instant and is_dead_wait_error(error):
        return 0, True
    return consecutive, False


def send_local_options(
    cwd: str,
    *,
    force: bool = False,
    model: Any | None = None,
    idempotency_key: str | None = None,
) -> dict[str, Any]:
    """Local send options. `force` expires a stuck run; do not set it on every send.

    Local Cursor Send v1 rejects a non-empty idempotency key ("only supported
    for cloud Send"). Job-driven turns still pass the key into `stream`; it is
    not placed on this payload.
    """
    del idempotency_key
    local: dict[str, Any] = {"cwd": cwd}
    if force:
        local["force"] = True
    payload: dict[str, Any] = {"local": local}
    if model is not None:
        to_json = getattr(model, "to_json", None)
        payload["model"] = to_json() if callable(to_json) else model
    return payload


def should_retry_dead_wait(
    *,
    streamed: int,
    status: str,
    error: str | None,
    duration_s: float,
) -> bool:
    """Retry the same prompt only when wait died instantly and nothing reached the thread."""
    if streamed > 0:
        return False
    _, recycle = note_auth_failures(
        0,
        status=status,
        error=error,
        duration_s=duration_s,
    )
    return recycle and is_dead_wait_error(error)


def dead_wait_owner_error(error: str | None, recycle: bool) -> str | None:
    if recycle and is_dead_wait_error(error):
        return DEAD_WAIT_NEXT_STEP
    return error


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


def log_cursor_turn_runs(
    product_run: str,
    sdk_run_ids: list[str],
    retry_reason: str | None,
) -> None:
    log.info(
        "cursor turn product_run=%s sdk_run_ids=%s retry_reason=%s",
        product_run or "-",
        ",".join(sdk_run_ids) or "-",
        retry_reason or "-",
    )


def current_product_run_id(runtime: Any, bot_id: str | None) -> str:
    from artek_buddy.observe import snapshot

    turn_id = snapshot().get("turn_id") or ""
    if turn_id:
        return turn_id
    resolve = getattr(runtime, "resolve_turn", None)
    if not callable(resolve):
        return ""
    found = resolve(bot_id)
    return str(getattr(found, "run_id", "") or "") if found is not None else ""
