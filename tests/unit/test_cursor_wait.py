from __future__ import annotations

from types import SimpleNamespace

from artek_buddy.runtime.cursor_wait import (
    CURSOR_AUTH_RECYCLE_AFTER,
    describe_cursor_wait,
    note_auth_failures,
    send_local_options,
    should_retry_dead_wait,
)


def test_describe_cursor_wait_stores_error_code_not_only_run_id() -> None:
    result = SimpleNamespace(
        status="error",
        result="",
        store=SimpleNamespace(
            error_code="Authentication error If you are logged in, try logging out and back in."
        ),
    )
    run = SimpleNamespace(id="run-dead")
    status, text, error = describe_cursor_wait(result, run)
    assert status == "failed"
    assert text is None
    assert error is not None
    assert "Authentication error" in error
    assert "run-dead" not in error


def test_describe_cursor_wait_completed_has_no_error() -> None:
    result = SimpleNamespace(status="completed", result="ok", store=None)
    status, text, error = describe_cursor_wait(result, SimpleNamespace(id="run-ok"))
    assert status == "completed"
    assert text == "ok"
    assert error is None


def test_describe_cursor_wait_without_code_omits_run_id() -> None:
    from artek_buddy.db.shaping import TURN_FAILED

    result = SimpleNamespace(status="error", result="", store=None, error=None)
    status, text, error = describe_cursor_wait(result, SimpleNamespace(id="run-dead"))
    assert status == "failed"
    assert error == TURN_FAILED
    assert "run-dead" not in (error or "")


def test_auth_recycle_after_n_instant_failures() -> None:
    n = 0
    recycle = False
    err = "Authentication error If you are logged in, try logging out and back in."
    for _ in range(CURSOR_AUTH_RECYCLE_AFTER):
        n, recycle = note_auth_failures(n, status="failed", error=err, duration_s=0.2)
    assert recycle is True
    assert n == CURSOR_AUTH_RECYCLE_AFTER


def test_single_auth_error_does_not_recycle() -> None:
    n, recycle = note_auth_failures(
        0,
        status="failed",
        error="Authentication error If you are logged in, try logging out and back in.",
        duration_s=0.1,
    )
    assert n == 1
    assert recycle is False


def test_completed_run_does_not_recycle() -> None:
    n, recycle = note_auth_failures(2, status="completed", error=None, duration_s=0.1)
    assert n == 0
    assert recycle is False


def test_instant_turn_failed_wait_recycles_immediately() -> None:
    from artek_buddy.db.shaping import TURN_FAILED

    n, recycle = note_auth_failures(0, status="failed", error=TURN_FAILED, duration_s=0.0)
    assert recycle is True
    assert n == 0


def test_slow_turn_failed_does_not_recycle() -> None:
    from artek_buddy.db.shaping import TURN_FAILED

    n, recycle = note_auth_failures(0, status="failed", error=TURN_FAILED, duration_s=5.0)
    assert recycle is False
    assert n == 0


def test_dead_wait_owner_error_names_the_next_step() -> None:
    from artek_buddy.db.shaping import TURN_FAILED
    from artek_buddy.runtime.cursor_wait import DEAD_WAIT_NEXT_STEP, dead_wait_owner_error

    assert dead_wait_owner_error(TURN_FAILED, True) == DEAD_WAIT_NEXT_STEP
    assert dead_wait_owner_error(TURN_FAILED, False) == TURN_FAILED


def test_send_local_options_omits_force_unless_asked() -> None:
    plain = send_local_options("/data/homes/bot")
    assert plain == {"local": {"cwd": "/data/homes/bot"}}
    assert "force" not in plain["local"]
    forced = send_local_options("/data/homes/bot", force=True)
    assert forced == {"local": {"cwd": "/data/homes/bot", "force": True}}


def test_should_retry_dead_wait_only_when_instant_and_silent() -> None:
    from artek_buddy.db.shaping import TURN_FAILED

    assert should_retry_dead_wait(
        streamed=0, status="failed", error=TURN_FAILED, duration_s=0.0
    )
    assert not should_retry_dead_wait(
        streamed=1, status="failed", error=TURN_FAILED, duration_s=0.0
    )
    assert not should_retry_dead_wait(
        streamed=0, status="failed", error=TURN_FAILED, duration_s=5.0
    )
    assert not should_retry_dead_wait(
        streamed=0, status="completed", error=None, duration_s=0.0
    )


def test_wait_error_logs_status_and_error_code(caplog) -> None:
    from artek_buddy.runtime.cursor_wait import log_cursor_wait

    with caplog.at_level("INFO", logger="artek_buddy"):
        log_cursor_wait(
            "run-dead",
            "ag-1",
            "error",
            0.2,
            "Authentication error If you are logged in, try logging out and back in.",
        )
    assert "status=error" in caplog.text
    assert "Authentication error" in caplog.text
