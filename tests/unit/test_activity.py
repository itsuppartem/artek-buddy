from __future__ import annotations

from artek_buddy.activity import (
    ActivityRecord,
    parse_activity_cursor,
    sanitize_activity_payload,
)


def test_sanitize_activity_payload_drops_secrets_and_screenshots() -> None:
    payload = {
        "id": "msg_1",
        "token": "secret_token_12345",
        "tool_args": {"cmd": "cat ~/.ssh/id_rsa"},
        "screenshot": "iVBORw0KGgo=",
        "nested": {"password": "hunter2", "ok": "visible"},
        "text": "Call with Bearer test_bearer_abc and code ABCD-EFGH",
    }
    sanitized = sanitize_activity_payload(payload)
    assert sanitized["id"] == "msg_1"
    assert "token" not in sanitized
    assert "tool_args" not in sanitized
    assert "screenshot" not in sanitized
    assert "password" not in sanitized["nested"]
    assert sanitized["nested"]["ok"] == "visible"
    assert "test_bearer_abc" not in sanitized["text"]
    assert "ABCD-EFGH" not in sanitized["text"]


def test_parse_activity_cursor_prefers_explicit_sequence() -> None:
    assert parse_activity_cursor("evt_1", "12", 7) == 7
    assert parse_activity_cursor("9", "evt_1", None) == 9
    assert parse_activity_cursor("evt_1", "4", None) == 4
    assert parse_activity_cursor("evt_1", "evt_2", None) is None


def test_activity_record_to_sse_uses_sequence_as_id() -> None:
    record = ActivityRecord(
        seq=3,
        id="act_x",
        event_type="message.created",
        event_version=1,
        actor="user",
        device_id=None,
        resource="bot_1",
        payload={"id": "msg_1"},
        created_at="2026-09-07T00:00:00Z",
    )
    frame = record.to_sse()
    assert frame.startswith("id: 3\n")
    assert "event: message.created\n" in frame
    assert '"seq": 3' in frame
