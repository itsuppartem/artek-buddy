from __future__ import annotations

import pytest

from artek_buddy.memory import (
    MemoryPathError,
    compact_thread_context,
    format_session_resume,
    normalize_memory_path,
    wrap_turn_prompt,
)
from artek_buddy.runtime.base import RuntimeBase


def test_normalize_memory_path_happy_and_fail() -> None:
    assert normalize_memory_path("entries/owner/note-1.md") == "entries/owner/note-1.md"
    assert normalize_memory_path("") == "MEMORY.md"
    with pytest.raises(MemoryPathError):
        normalize_memory_path("../secret")
    with pytest.raises(MemoryPathError):
        normalize_memory_path("/etc/passwd")


def test_wrap_turn_prompt_lead_mentions_takeover_and_slim_observe() -> None:
    wrapped = wrap_turn_prompt("hi", None, role="lead")
    assert "request_takeover" in wrapped
    assert "include_image" in wrapped
    assert "message_bot" in wrapped
    assert "once per fact" in wrapped
    assert "list_apps" in wrapped
    assert "connect_app" in wrapped


def test_wrap_turn_prompt_lead_dispatches_and_worker_stays_silent() -> None:
    lead = wrap_turn_prompt("hi", None, role="lead")
    worker = wrap_turn_prompt("do the long job", None, role="subagent")
    assert "spawn_subagent" in lead
    assert "finish this dispatch turn" in lead
    assert "You do not have run_owner_command" in lead
    assert "Do not post to the owner chat" in worker
    assert "does not appear in the owner thread" in worker
    assert "You do not have send_message" in worker
    assert worker.count("send_message") == 1
    assert "no text update" in lead
    assert "status-only ping must inspect" in lead


def test_wrap_turn_prompt_keeps_user_tail() -> None:
    wrapped = wrap_turn_prompt("remember this city", "Belgrade is the capital")
    assert wrapped.endswith("remember this city")
    assert "Belgrade is the capital" in wrapped


def test_wrap_turn_prompt_includes_thread_before_user() -> None:
    wrapped = wrap_turn_prompt(
        "continue",
        None,
        thread_context="This chat, recent messages:\nuser: the fox count is seven",
    )
    assert wrapped.endswith("continue")
    assert "the fox count is seven" in wrapped
    assert wrapped.strip() != "continue"


def test_compact_thread_context_caps_bytes() -> None:
    from types import SimpleNamespace

    messages = [
        SimpleNamespace(
            id=f"m{index}",
            role="user",
            blocks=[SimpleNamespace(kind="text", text="x" * 400)],
        )
        for index in range(40)
    ]
    text = compact_thread_context(messages, cap=500)
    assert text.startswith("This chat, recent messages:")
    assert len(text.encode("utf-8")) <= 500


def test_compact_thread_context_deduplicates_failed_user_lines_and_excludes_current_run() -> None:
    from types import SimpleNamespace

    messages = [
        SimpleNamespace(
            id="m1",
            run_id="run_old_1",
            role="user",
            blocks=[SimpleNamespace(kind="text", text="continue the task")],
        ),
        SimpleNamespace(
            id="m2",
            run_id="run_old_2",
            role="user",
            blocks=[SimpleNamespace(kind="text", text="continue the task")],
        ),
        SimpleNamespace(
            id="m3",
            run_id="run_current",
            role="user",
            blocks=[SimpleNamespace(kind="text", text="what is the status?")],
        ),
    ]

    text = compact_thread_context(messages, exclude_run_id="run_current")

    assert text.count("user: continue the task") == 1
    assert "what is the status?" not in text


def test_session_resume_is_bounded_redacted_and_uses_existing_facts(monkeypatch) -> None:
    from types import SimpleNamespace

    monkeypatch.setenv("AGENT_HTTP_TOKEN", "host-token-secret")
    bot = SimpleNamespace(
        title="Repository caretaker",
        description="Keep the current branch reviewable.",
        instructions="Do not force-push.\nPreserve Postgres data.",
    )
    messages = [
        SimpleNamespace(
            role="bot",
            blocks=[
                SimpleNamespace(
                    kind="text",
                    text="Last result: branch feature/rpc is clean; token host-token-secret was hidden.",
                )
            ],
        )
    ]
    memory = """
<owner_book>
## paths
Repository path: ~/work/artek-buddy
</owner_book>
<work_notes>
## current
Branch: feature/rpc
</work_notes>
"""

    brief = format_session_resume(
        home_cwd="/data/homes/workhorse",
        bot=bot,
        memory_context=memory,
        messages=messages,
        max_bytes=700,
    )

    assert brief is not None
    assert "<session_resume>" in brief
    assert "workspace: /data/homes/workhorse" in brief
    assert "Branch: feature/rpc" in brief
    assert "Do not force-push." in brief
    assert "Last result:" in brief
    assert "host-token-secret" not in brief
    assert "[redacted]" in brief
    assert len(brief.encode("utf-8")) <= 700


def test_fresh_session_marker_is_consumed_once(tmp_path) -> None:
    from types import SimpleNamespace

    settings = SimpleNamespace(
        agent_data_dir=str(tmp_path / "data"),
        agent_cwd=str(tmp_path / "workspace"),
    )
    runtime = RuntimeBase(settings)

    runtime.mark_session_fresh("agent_1")

    assert runtime.consume_session_fresh("agent_1") is True
    assert runtime.consume_session_fresh("agent_1") is False
