from __future__ import annotations

from artek_buddy.contracts.domain import ThreadSendInput
from artek_buddy.db.history.commands import owner_command_fingerprint


def test_thread_send_input_accepts_command_id() -> None:
    body = ThreadSendInput(text="hello", command_id="cmd_abc", parent_command_id="cmd_prev")
    assert body.command_id == "cmd_abc"
    assert body.parent_command_id == "cmd_prev"
    owner = ThreadSendInput(text="hello")
    assert owner.command_id is None


def test_owner_command_fingerprint_changes_with_text() -> None:
    first = owner_command_fingerprint("hello")
    second = owner_command_fingerprint("hello")
    other = owner_command_fingerprint("other")
    assert first == second
    assert first != other
