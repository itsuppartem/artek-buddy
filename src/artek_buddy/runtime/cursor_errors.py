from __future__ import annotations

import logging
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from typing import Any

import cursor_sdk
from cursor_sdk import AgentBusyError, CursorAgentError

from artek_buddy.runtime.cursor_wait import CURSOR_AUTH_ERROR_HINT
from artek_buddy.runtime.types import AgentRuntimeError, AgentRuntimeExhausted

log = logging.getLogger("artek_buddy")

QUOTA_EXHAUSTED_TEXT = "The model quota is exhausted. Wait and try again."
CURSOR_KEY_INVALID_TEXT = "Open Models and check the Cursor key."

RATE_LIMIT_MAX_WAIT_S = 60.0
RATE_LIMIT_BACKOFF_BASE_S = 1.0

_RateLimitError = getattr(cursor_sdk, "RateLimitError", None)
_AuthenticationError = getattr(cursor_sdk, "AuthenticationError", None)

_RATE_LIMIT_CODES = frozenset(
    {
        "rate_limit",
        "rate_limit_exceeded",
        "usage_limit_exceeded",
        "sdk_error_code_rate_limit_exceeded",
        "sdk_error_code_usage_limit_exceeded",
    }
)
_AUTH_CODES = frozenset(
    {
        "unauthorized",
        "unauthenticated",
        "authentication_error",
        "api_key_not_found",
        "sdk_error_code_unauthorized",
        "sdk_error_code_api_key_not_found",
    }
)


def _error_status(err: BaseException) -> int | None:
    status = getattr(err, "status", None)
    if status is None:
        status = getattr(err, "status_code", None)
    try:
        return int(status) if status is not None else None
    except (TypeError, ValueError):
        return None


def _error_code(err: BaseException) -> str:
    raw = getattr(err, "code", None) or getattr(err, "proto_error_code", None) or ""
    return str(raw).strip().lower()


def _error_message(err: BaseException) -> str:
    return str(getattr(err, "message", None) or err)


def _request_id(err: BaseException) -> str | None:
    value = getattr(err, "request_id", None)
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def sdk_error_retryable(err: BaseException) -> bool:
    return bool(getattr(err, "is_retryable", False))


def is_rate_limited(err: BaseException) -> bool:
    if isinstance(err, AgentBusyError):
        return False
    if _RateLimitError is not None and isinstance(err, _RateLimitError):
        return True
    if _error_status(err) == 429:
        return True
    return _error_code(err) in _RATE_LIMIT_CODES


def is_auth_failure(err: BaseException) -> bool:
    if isinstance(err, AgentBusyError) or is_rate_limited(err):
        return False
    if _AuthenticationError is not None and isinstance(err, _AuthenticationError):
        return True
    if _error_status(err) == 401:
        return True
    if _error_code(err) in _AUTH_CODES:
        return True
    return CURSOR_AUTH_ERROR_HINT in _error_message(err).lower()


def parse_retry_after(raw: Any) -> float | None:
    if raw is None or isinstance(raw, bool):
        return None
    if isinstance(raw, int | float):
        if raw != raw:  # NaN
            return None
        return max(0.0, float(raw))
    total = getattr(raw, "total_seconds", None)
    if callable(total):
        try:
            return max(0.0, float(total()))
        except (TypeError, ValueError):
            return None
    seconds = getattr(raw, "seconds", None)
    if seconds is not None and not isinstance(raw, str | bytes):
        try:
            nanos = getattr(raw, "nanos", 0) or 0
            return max(0.0, float(seconds) + float(nanos) / 1_000_000_000)
        except (TypeError, ValueError):
            return None
    text = str(raw).strip()
    if not text:
        return None
    try:
        return max(0.0, float(text))
    except ValueError:
        pass
    try:
        when = parsedate_to_datetime(text)
    except (TypeError, ValueError, OverflowError):
        return None
    if when.tzinfo is None:
        when = when.replace(tzinfo=UTC)
    return max(0.0, (when - datetime.now(UTC)).total_seconds())


def rate_limit_wait_seconds(err: BaseException, attempt: int = 0) -> float:
    parsed = parse_retry_after(getattr(err, "retry_after", None))
    if parsed is not None:
        return min(parsed, RATE_LIMIT_MAX_WAIT_S)
    backoff = RATE_LIMIT_BACKOFF_BASE_S * (2 ** max(0, attempt))
    return min(backoff, RATE_LIMIT_MAX_WAIT_S)


def log_cursor_agent_error(err: BaseException) -> None:
    log.error(
        "run did not start: %s retryable=%s request_id=%s",
        _error_message(err),
        getattr(err, "is_retryable", None),
        _request_id(err),
    )


def map_cursor_agent_error(err: BaseException) -> AgentRuntimeError:
    request_id = _request_id(err)
    if is_auth_failure(err):
        return AgentRuntimeError(
            CURSOR_KEY_INVALID_TEXT,
            category="permanent",
            retryable=False,
            request_id=request_id,
        )
    if is_rate_limited(err):
        return AgentRuntimeExhausted(QUOTA_EXHAUSTED_TEXT, request_id=request_id)
    return AgentRuntimeError(
        _error_message(err),
        retryable=sdk_error_retryable(err),
        request_id=request_id,
    )


def should_retry_rate_limit(err: BaseException, *, retried: bool) -> bool:
    return is_rate_limited(err) and sdk_error_retryable(err) and not retried
