from __future__ import annotations

import logging
from typing import Any

log = logging.getLogger("artek_buddy")

ACTIVITY_KINDS = frozenset(
    {"run_started", "tool_started", "tool_finished", "text", "clarification", "progress"}
)


def touch_worker_activity(
    runtime: Any,
    run_id: str | None,
    *,
    kind: str,
    tool_name: str | None = None,
    tool_running: bool | None = None,
) -> None:
    if not run_id or kind not in ACTIVITY_KINDS:
        return
    store = getattr(runtime, "store", None)
    record = getattr(store, "record_subagent_activity", None)
    if not callable(record):
        return
    try:
        record(run_id, kind=kind, tool_name=tool_name, tool_running=tool_running)
    except Exception:
        log.exception("failed to persist worker activity")
