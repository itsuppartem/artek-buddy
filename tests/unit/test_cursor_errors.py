from __future__ import annotations

from types import SimpleNamespace

from cursor_sdk import AgentBusyError, CursorAgentError

from artek_buddy.db.shaping import TURN_FAILED, owner_visible_error
from artek_buddy.runtime.cursor_errors import (
    CURSOR_KEY_INVALID_TEXT,
    CURSOR_TIMEOUT_TEXT,
    QUOTA_EXHAUSTED_TEXT,
    is_auth_failure,
    is_rate_limited,
    is_timeout,
    map_cursor_agent_error,
    parse_retry_after,
    rate_limit_wait_seconds,
    sdk_error_retryable,
    should_retry_rate_limit,
)
from artek_buddy.runtime.types import AgentRuntimeExhausted, AgentRuntimeTimeout


def test_owner_visible_error_keeps_quota_and_auth_copy() -> None:
    assert owner_visible_error(QUOTA_EXHAUSTED_TEXT) == QUOTA_EXHAUSTED_TEXT
    assert owner_visible_error(CURSOR_KEY_INVALID_TEXT) == CURSOR_KEY_INVALID_TEXT
    assert owner_visible_error(QUOTA_EXHAUSTED_TEXT) != TURN_FAILED
    assert owner_visible_error(CURSOR_KEY_INVALID_TEXT) != TURN_FAILED


def test_busy_is_not_a_rate_limit() -> None:
    try:
        busy = AgentBusyError("agent busy")
    except TypeError:
        busy = AgentBusyError("agent busy", status=409)
    assert is_rate_limited(busy) is False
    assert is_auth_failure(busy) is False
    assert should_retry_rate_limit(busy, retried=False) is False


def test_retry_after_zero_is_waited_then_retry_once() -> None:
    err = CursorAgentError("rate limited", status=429)
    try:
        err.retry_after = 0
        err.is_retryable = True
    except (AttributeError, TypeError):
        err = SimpleNamespace(
            status=429,
            retry_after=0,
            is_retryable=True,
            message="rate limited",
        )
    assert is_rate_limited(err) is True
    assert rate_limit_wait_seconds(err, 0) == 0.0
    assert should_retry_rate_limit(err, retried=False) is True
    assert should_retry_rate_limit(err, retried=True) is False


def test_missing_retry_after_uses_bounded_backoff() -> None:
    err = SimpleNamespace(status=429, retry_after=None, is_retryable=True)
    assert rate_limit_wait_seconds(err, 0) == 1.0
    assert rate_limit_wait_seconds(err, 1) == 2.0
    huge = SimpleNamespace(status=429, retry_after=3600, is_retryable=True)
    assert rate_limit_wait_seconds(huge, 0) == 60.0


def test_parse_retry_after_seconds_and_blank() -> None:
    assert parse_retry_after(0) == 0.0
    assert parse_retry_after("0.01") == 0.01
    assert parse_retry_after(None) is None
    assert parse_retry_after("") is None


def test_non_retryable_rate_limit_maps_to_exhausted_without_retry() -> None:
    err = SimpleNamespace(
        status=429,
        retry_after=0,
        is_retryable=False,
        message="rate limited",
        request_id="req-nr",
    )
    assert should_retry_rate_limit(err, retried=False) is False
    mapped = map_cursor_agent_error(err)
    assert isinstance(mapped, AgentRuntimeExhausted)
    assert mapped.retryable is True
    assert mapped.message == QUOTA_EXHAUSTED_TEXT
    assert sdk_error_retryable(err) is False


def test_api_timeout_maps_to_retryable_owner_copy() -> None:
    from cursor_sdk import APITimeoutError

    err = APITimeoutError("request timed out", request_id="req-to")
    assert is_timeout(err) is True
    assert is_rate_limited(err) is False
    assert should_retry_rate_limit(err, retried=False) is False
    mapped = map_cursor_agent_error(err)
    assert isinstance(mapped, AgentRuntimeTimeout)
    assert mapped.retryable is True
    assert mapped.message == CURSOR_TIMEOUT_TEXT
    assert mapped.request_id == "req-to"
    assert owner_visible_error(mapped.message) == CURSOR_TIMEOUT_TEXT
    assert owner_visible_error(mapped.message) != TURN_FAILED
