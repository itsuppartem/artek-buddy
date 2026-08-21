from __future__ import annotations

import pytest

from artek_buddy.memory import (
    MemoryPathError,
    compact_thread_context,
    normalize_memory_path,
    wrap_turn_prompt,
)


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
