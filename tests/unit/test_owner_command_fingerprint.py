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


def test_owner_command_fingerprint_covers_attachment_bytes() -> None:
    one = {"name": "report.txt", "content_base64": "b25l"}
    two = {"name": "report.txt", "content_base64": "dHdv"}
    same = owner_command_fingerprint("read it", attachments=[one])
    again = owner_command_fingerprint("read it", attachments=[one])
    changed = owner_command_fingerprint("read it", attachments=[two])
    assert one["content_base64"] != two["content_base64"]
    assert same == again
    assert same != changed


def test_owner_command_fingerprint_ignores_inline_file_order() -> None:
    first = {"name": "a.txt", "content_base64": "YQ=="}
    second = {"name": "b.txt", "content_base64": "Yg=="}
    left = owner_command_fingerprint("pair", attachments=[first, second])
    right = owner_command_fingerprint("pair", attachments=[second, first])
    assert left == right


def test_owner_command_fingerprint_ids_ignore_order() -> None:
    left = owner_command_fingerprint("see", attachment_ids=["art_b", "art_a"])
    right = owner_command_fingerprint("see", attachment_ids=["art_a", "art_b"])
    assert left == right


def test_owner_command_fingerprint_does_not_embed_raw_base64() -> None:
    digest = owner_command_fingerprint(
        "read it",
        attachments=[{"name": "report.txt", "content_base64": "b25l"}],
    )
    assert "b25l" not in digest
