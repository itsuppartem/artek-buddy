from __future__ import annotations

from types import SimpleNamespace

from artek_buddy.memory import format_subagent_context
from artek_buddy.runtime.owner_intent import classify_owner_intent


def test_status_ping_is_not_a_stop_intent() -> None:
    assert classify_owner_intent("please e2e-worker-status") == "status"
    assert classify_owner_intent("как там?") == "status"
    assert classify_owner_intent("what is happening") == "status"
    assert classify_owner_intent("please e2e-worker-false-idle") == "status"


def test_correction_intent_beats_status_words() -> None:
    assert classify_owner_intent("please e2e-worker-steer use path B") == "correction"


def test_stale_stop_probe_is_not_status() -> None:
    assert classify_owner_intent("please e2e-worker-stale-stop") == "other"


def test_format_subagent_context_names_empty_progress_as_no_text_update() -> None:
    text = format_subagent_context(
        [
            SimpleNamespace(
                index=1,
                name="Researcher",
                id="sub_abc",
                status="running",
                task="long job",
                progress=None,
                last_activity_kind="tool_finished",
                activity_seq=21,
                last_tool_name="list_subagents",
                tool_running=False,
                last_activity_at="2026-09-01T12:00:00.000000Z",
                clarifications=None,
            )
        ]
    )
    assert text is not None
    assert "no text update" in text
    assert "seq=21" in text
    assert "tool_finished" in text
    assert " idle" not in text.lower()


def test_format_subagent_context_includes_reported_step() -> None:
    text = format_subagent_context(
        [
            SimpleNamespace(
                index=1,
                name="Researcher",
                id="sub_abc",
                status="running",
                task="long job",
                progress="commit",
                progress_remaining="push MR 76",
                last_activity_kind="progress",
                activity_seq=3,
                last_tool_name="report_progress",
                tool_running=False,
                last_activity_at="2026-09-02T10:00:00.000000Z",
                clarifications=None,
            )
        ]
    )
    assert text is not None
    assert "step: commit" in text
    assert "remaining: push MR 76" in text
    assert "no text update" not in text
