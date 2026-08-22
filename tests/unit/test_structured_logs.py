from __future__ import annotations

import json
import logging
from io import StringIO

from artek_buddy.observe import (
    JsonFormatter,
    bind_turn,
    log_event,
    log_tool,
    mint_request_id,
    redact_text,
    tool_result_summary,
    unbind_turn,
)


def test_redact_host_token_and_bearer() -> None:
    token = "ci-host-token-aabbccddeeff001122334455"
    text = redact_text(f"Authorization: Bearer {token} path=/home/artek/notes")
    assert token not in text
    assert "Bearer [redacted]" in text
    assert "/home/[user]" in text


def test_redact_novnc_and_database_url() -> None:
    text = redact_text(
        "GET /novnc/vnc.html?token=abc postgresql://artek:super-secret@127.0.0.1:5432/db"
    )
    assert "/novnc/[redacted]" in text
    assert "super-secret" not in text
    assert "postgresql://artek:[redacted]@" in text


def test_redact_pairing_code_and_device_token() -> None:
    text = redact_text("code ABCD-EFGH token dev_" + ("a" * 32))
    assert "ABCD-EFGH" not in text
    assert "dev_[redacted]" in text


def test_tool_summary_does_not_keep_screenshot() -> None:
    assert (
        tool_result_summary({"ok": True, "screenshot": "iVBORw0KGgoAAAANSUhEUg==", "_data": b"x"})
        == "ok"
    )
    assert (
        tool_result_summary({"ok": False, "error": "denied by owner", "denied": True}) == "denied"
    )


def test_json_formatter_includes_request_id() -> None:
    record = logging.LogRecord(
        name="artek_buddy",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="threads.send",
        args=(),
        exc_info=None,
    )
    record.request_id = "req_deadbeef"
    record.turn_id = "run_1"
    record.event = "threads.send"
    payload = json.loads(JsonFormatter().format(record))
    assert payload["msg"] == "threads.send"
    assert payload["request_id"] == "req_deadbeef"
    assert payload["turn_id"] == "run_1"


def test_send_and_tool_share_request_id(caplog) -> None:
    request_id = mint_request_id()
    turn_id = "run_observe_1"
    bind_turn(turn_id, request_id, bot_id="bot_1", thread_id="thr_1", runtime="scripted")
    caplog.set_level(logging.INFO, logger="artek_buddy")
    try:
        log_event(
            "threads.send",
            request_id=request_id,
            bot_id="bot_1",
            thread_id="thr_1",
            turn_id=turn_id,
            runtime="scripted",
            result="started",
        )
        log_tool(
            "remember",
            {"ok": True, "screenshot": "nope"},
            latency_ms=4,
            runtime="scripted",
            bot_id="bot_1",
            turn_id=turn_id,
            thread_id="thr_1",
        )
    finally:
        unbind_turn(turn_id)
    text = caplog.text
    assert request_id in text
    assert "threads.send" in text
    assert "remember" in text
    assert "nope" not in text
    assert "ci-host-token-aabbccddeeff001122334455" not in text


def test_json_log_line_redacts_token() -> None:
    stream = StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(JsonFormatter())
    logger = logging.getLogger("artek_buddy.observe_test_json")
    logger.handlers = [handler]
    logger.propagate = False
    logger.setLevel(logging.INFO)
    logger.info("token=%s", "ci-host-token-aabbccddeeff001122334455")
    line = stream.getvalue()
    assert "ci-host-token-aabbccddeeff001122334455" not in line
    assert "[redacted]" in line
