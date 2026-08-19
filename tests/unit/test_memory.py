from __future__ import annotations

import pytest

from artek_buddy.memory import MemoryPathError, normalize_memory_path, wrap_turn_prompt


def test_normalize_memory_path_happy_and_fail() -> None:
    assert normalize_memory_path("entries/owner/note-1.md") == "entries/owner/note-1.md"
    assert normalize_memory_path("") == "MEMORY.md"
    with pytest.raises(MemoryPathError):
        normalize_memory_path("../secret")
    with pytest.raises(MemoryPathError):
        normalize_memory_path("/etc/passwd")


def test_wrap_turn_prompt_keeps_user_tail() -> None:
    wrapped = wrap_turn_prompt("remember this city", "Belgrade is the capital")
    assert wrapped.endswith("remember this city")
    assert "Belgrade is the capital" in wrapped
