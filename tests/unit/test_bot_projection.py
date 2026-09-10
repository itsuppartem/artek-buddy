from __future__ import annotations

from artek_buddy.bot_attention import (
    BotAttentionFacts,
    attention_reason_for,
    execution_state_for,
    merge_bot_projection,
    pending_ask_id_from_blocks,
    project_bot,
)
from artek_buddy.contracts.domain import Bot


def _bot(**extra: object) -> Bot:
    payload = {
        "id": "bot_1",
        "workspace_id": "ws_1",
        "name": "Mail",
        "title": "",
        "description": "",
        "instructions": "",
        "color": "#2864dc",
        "notify_on_finish": True,
        "pinned": False,
        "archived_at": None,
        "unread": True,
        "parent_bot_id": None,
        "thread_id": "thr_1",
        "preview": "No questions remain",
        "status": "idle",
        "computer_mode": "team",
        "updated_at": "2026-09-09T12:00:00.000000Z",
        "created_at": "2026-09-09T12:00:00.000000Z",
    }
    payload.update(extra)
    return Bot.model_validate(payload)


def test_preview_question_does_not_create_attention() -> None:
    bot = project_bot(_bot(), BotAttentionFacts(result_id="run_done", result_status="completed"))
    assert bot.attention_reason == "none"
    assert bot.execution_state == "completed"
    assert bot.result_id == "run_done"
    assert bot.result_status == "completed"
    assert "question" in bot.preview.lower()


def test_waiting_input_without_a_pending_card_is_not_a_decision() -> None:
    assert attention_reason_for(active_run_status="waiting_input") == "none"
    assert execution_state_for("idle", active_run_status="waiting_input") == "waiting"


def test_idle_last_failed_run_is_failed_not_completed() -> None:
    assert execution_state_for("idle", result_status="failed") == "failed"
    assert execution_state_for("idle", result_status="cancelled") == "cancelled"
    assert execution_state_for("idle", result_status="completed") == "completed"


def test_idle_with_no_runs_is_not_completed() -> None:
    assert execution_state_for("idle") == "unknown"
    assert execution_state_for("sleeping") == "unknown"
    assert execution_state_for("") == "unknown"
    assert execution_state_for("idle", active_run_status="unknown") == "unconfirmed"


def test_consent_ask_and_takeover_map_without_preview() -> None:
    assert attention_reason_for(pending_consent_id="cns_1") == "approval"
    assert attention_reason_for(pending_ask_id="msg_1") == "clarification"
    assert attention_reason_for(active_run_status="waiting_takeover") == "takeover"
    assert attention_reason_for(pending_owner_job_id="job_1") == "recovery"
    assert attention_reason_for(pending_recovery_id="msg_rec") == "recovery"
    assert attention_reason_for(active_run_status="waiting_recovery") == "recovery"


def test_takeover_wins_over_consent() -> None:
    assert (
        attention_reason_for(
            active_run_status="waiting_takeover",
            pending_consent_id="cns_1",
            pending_ask_id="msg_1",
        )
        == "takeover"
    )


def test_previous_result_survives_a_new_run() -> None:
    bot = project_bot(
        _bot(status="running", unread=True),
        BotAttentionFacts(
            active_run_id="run_new",
            active_run_status="running",
            result_id="run_old",
            result_status="completed",
            state_version=4,
        ),
    )
    assert bot.execution_state == "running"
    assert bot.result_id == "run_old"
    assert bot.attention_reason == "none"


def test_late_snapshot_does_not_undo_accepted_decision() -> None:
    decided = _bot(
        attention_reason="none",
        execution_state="running",
        state_version=12,
        pending_consent_id=None,
    )
    stale = _bot(
        attention_reason="approval",
        execution_state="waiting",
        state_version=9,
        pending_consent_id="cns_old",
    )
    merged = merge_bot_projection(decided, stale)
    assert merged.attention_reason == "none"
    assert merged.execution_state == "running"
    assert merged.pending_consent_id is None
    assert merged.state_version == 12


def test_equal_version_snapshot_applies() -> None:
    current = _bot(attention_reason="approval", state_version=5, pending_consent_id="cns_1")
    incoming = _bot(attention_reason="none", state_version=5, pending_consent_id=None)
    merged = merge_bot_projection(current, incoming)
    assert merged.attention_reason == "none"


def test_lost_connection_does_not_fail_execution() -> None:
    bot = project_bot(
        _bot(status="running"),
        BotAttentionFacts(active_run_status="running"),
        connection_state="last_known",
    )
    assert bot.execution_state == "running"
    assert bot.connection_state == "last_known"
    assert bot.attention_reason == "none"


def test_pending_ask_blocks_ignore_answered_cards() -> None:
    assert pending_ask_id_from_blocks([{"kind": "ask", "text": "Which city?", "status": "pending"}])
    assert not pending_ask_id_from_blocks(
        [{"kind": "ask", "text": "Which city?", "status": "answered"}]
    )
    assert not pending_ask_id_from_blocks([{"kind": "text", "text": "question"}])
