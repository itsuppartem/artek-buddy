"""Today projection: execution, attention, and connection stay separate."""

from __future__ import annotations

import json
from dataclasses import dataclass

from artek_buddy.contracts.domain import AttentionReason, Bot, ConnectionState, ExecutionState

ACTIVE_RUN_STATUSES = frozenset(
    {"queued", "leased", "running", "waiting_input", "waiting_takeover"}
)
TERMINAL_RUN_STATUSES = frozenset({"completed", "failed", "cancelled"})

_STATUS_TO_EXECUTION: dict[str, ExecutionState] = {
    "queued": "queued",
    "leased": "queued",
    "running": "running",
    "waiting_input": "waiting",
    "waiting_takeover": "waiting",
    "needs_you": "waiting",
    "completed": "completed",
    "failed": "failed",
    "cancelled": "cancelled",
    "idle": "completed",
    "sleeping": "completed",
    "suspended": "completed",
    "done": "completed",
    "": "completed",
}


@dataclass(frozen=True, slots=True)
class BotAttentionFacts:
    active_run_id: str | None = None
    active_run_status: str | None = None
    result_id: str | None = None
    result_status: str | None = None
    pending_consent_id: str | None = None
    pending_ask_id: str | None = None
    pending_owner_job_id: str | None = None
    state_version: int = 0


def execution_state_for(
    bot_status: str,
    *,
    active_run_status: str | None = None,
    result_status: str | None = None,
) -> ExecutionState:
    if active_run_status:
        mapped = _STATUS_TO_EXECUTION.get(active_run_status)
        if mapped is not None:
            return mapped
        return "unknown"
    mapped = _STATUS_TO_EXECUTION.get((bot_status or "").strip().lower())
    if mapped is not None:
        return mapped
    if result_status in TERMINAL_RUN_STATUSES:
        return _STATUS_TO_EXECUTION[result_status]
    return "unknown"


def attention_reason_for(
    *,
    active_run_status: str | None = None,
    bot_status: str = "",
    pending_consent_id: str | None = None,
    pending_ask_id: str | None = None,
    pending_owner_job_id: str | None = None,
) -> AttentionReason:
    status = (active_run_status or bot_status or "").strip().lower()
    if status == "waiting_takeover":
        return "takeover"
    if pending_consent_id:
        return "approval"
    if pending_ask_id:
        return "clarification"
    if pending_owner_job_id:
        return "recovery"
    return "none"


def project_bot(
    bot: Bot,
    facts: BotAttentionFacts,
    *,
    connection_state: ConnectionState = "live",
) -> Bot:
    execution = execution_state_for(
        bot.status,
        active_run_status=facts.active_run_status,
        result_status=facts.result_status,
    )
    attention = attention_reason_for(
        active_run_status=facts.active_run_status,
        bot_status=bot.status,
        pending_consent_id=facts.pending_consent_id,
        pending_ask_id=facts.pending_ask_id,
        pending_owner_job_id=facts.pending_owner_job_id,
    )
    takeover_id = facts.active_run_id if facts.active_run_status == "waiting_takeover" else None
    if bot.status == "waiting_takeover" and takeover_id is None:
        takeover_id = facts.active_run_id
    return bot.model_copy(
        update={
            "execution_state": execution,
            "attention_reason": attention,
            "connection_state": connection_state,
            "state_version": max(0, int(facts.state_version)),
            "pending_consent_id": facts.pending_consent_id,
            "pending_ask_id": facts.pending_ask_id,
            "takeover_run_id": takeover_id,
            "result_id": facts.result_id,
        }
    )


def merge_bot_projection(current: Bot, incoming: Bot) -> Bot:
    """Ignore a late snapshot that would undo a newer attention/execution decision."""
    if incoming.state_version < current.state_version:
        return current
    return incoming


def pending_ask_id_from_blocks(blocks: object) -> bool:
    if isinstance(blocks, str):
        try:
            blocks = json.loads(blocks)
        except json.JSONDecodeError:
            return False
    if not isinstance(blocks, list):
        return False
    for block in blocks:
        if not isinstance(block, dict) or block.get("kind") != "ask":
            continue
        if block.get("status") != "answered":
            return True
    return False
