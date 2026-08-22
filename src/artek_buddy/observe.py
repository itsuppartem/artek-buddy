from __future__ import annotations

import json
import logging
import os
import re
import threading
import time
from collections.abc import Callable
from contextvars import ContextVar, Token
from pathlib import Path
from typing import Any

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from artek_buddy.auth import PAIRING_ALPHABET
from artek_buddy.db.shaping import new_id

log = logging.getLogger("artek_buddy")

FIELD_KEYS = (
    "request_id",
    "bot_id",
    "thread_id",
    "turn_id",
    "runtime",
    "tool",
    "latency_ms",
    "result",
    "event",
    "method",
    "path",
    "status",
)

_request_id: ContextVar[str | None] = ContextVar("observe_request_id", default=None)
_bot_id: ContextVar[str | None] = ContextVar("observe_bot_id", default=None)
_thread_id: ContextVar[str | None] = ContextVar("observe_thread_id", default=None)
_turn_id: ContextVar[str | None] = ContextVar("observe_turn_id", default=None)
_runtime: ContextVar[str | None] = ContextVar("observe_runtime", default=None)

_lock = threading.Lock()
_request_by_turn: dict[str, str] = {}

_INCOMING_ID = re.compile(r"^[A-Za-z0-9._-]{8,80}$")
_BEARER = re.compile(r"(?i)(bearer)\s+\S+")
_NOVNC = re.compile(r"/novnc/\S+")
_HOME = re.compile(r"/home/[^/\s]+")
_PG = re.compile(r"(postgres(?:ql)?://[^:/]+:)[^@\s]+(@)")
_DEVICE = re.compile(r"\bdev_[A-Za-z0-9_-]{16,}\b")
_PAIRING = re.compile(
    rf"\b[{re.escape(PAIRING_ALPHABET)}]{{4}}-[{re.escape(PAIRING_ALPHABET)}]{{4}}\b"
)
_SKIP_HTTP_PATHS = {"/health"}


def mint_request_id() -> str:
    return new_id("req")


def accept_request_id(raw: str | None) -> str:
    text = (raw or "").strip()
    if _INCOMING_ID.fullmatch(text):
        return text
    return mint_request_id()


def current_request_id() -> str | None:
    return _request_id.get()


def request_id_for_turn(turn_id: str | None) -> str | None:
    if not turn_id:
        return None
    with _lock:
        return _request_by_turn.get(turn_id)


def bind_request(request_id: str) -> Token[str | None]:
    return _request_id.set(request_id)


def reset_request(token: Token[str | None]) -> None:
    _request_id.reset(token)


def bind_turn(
    turn_id: str | None,
    request_id: str | None,
    *,
    bot_id: str | None = None,
    thread_id: str | None = None,
    runtime: str | None = None,
) -> None:
    if turn_id and request_id:
        with _lock:
            _request_by_turn[turn_id] = request_id
    if request_id:
        _request_id.set(request_id)
    if bot_id is not None:
        _bot_id.set(bot_id)
    if thread_id is not None:
        _thread_id.set(thread_id)
    if turn_id is not None:
        _turn_id.set(turn_id)
    if runtime is not None:
        _runtime.set(runtime)


def unbind_turn(turn_id: str | None) -> None:
    if turn_id:
        with _lock:
            _request_by_turn.pop(turn_id, None)


def snapshot() -> dict[str, str]:
    turn_id = _turn_id.get() or ""
    request_id = _request_id.get() or ""
    if not request_id and turn_id:
        request_id = request_id_for_turn(turn_id) or ""
    return {
        "request_id": request_id,
        "bot_id": _bot_id.get() or "",
        "thread_id": _thread_id.get() or "",
        "turn_id": turn_id,
        "runtime": _runtime.get() or "",
    }


def _secrets() -> list[str]:
    found: list[str] = []
    for key in (
        "AGENT_HTTP_TOKEN",
        "CURSOR_API_KEY",
        "SANDBOX_SUPERVISOR_TOKEN",
        "MEMORY_DB_PASSWORD",
    ):
        value = os.environ.get(key, "").strip()
        if len(value) >= 6:
            found.append(value)
    return found


def redact_text(text: str) -> str:
    if not text:
        return text
    out = text
    for secret in _secrets():
        if secret in out:
            out = out.replace(secret, "[redacted]")
    out = _BEARER.sub(r"\1 [redacted]", out)
    out = _NOVNC.sub("/novnc/[redacted]", out)
    out = _HOME.sub("/home/[user]", out)
    out = _PG.sub(r"\1[redacted]\2", out)
    out = _DEVICE.sub("dev_[redacted]", out)
    return _PAIRING.sub("[redacted]", out)


def tool_result_summary(result: dict[str, Any] | None) -> str:
    if not result:
        return "error"
    if result.get("denied"):
        return "denied"
    if result.get("ok") is False:
        return "error"
    return "ok"


def resolved_log_format(explicit: str | None = None) -> str:
    raw = (explicit if explicit is not None else os.environ.get("LOG_FORMAT", "")).strip().lower()
    if raw in {"json", "text"}:
        return raw
    return "json" if Path("/.dockerenv").exists() else "text"


class ContextFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        for key, value in snapshot().items():
            if not getattr(record, key, None):
                setattr(record, key, value)
        for key in FIELD_KEYS:
            if not hasattr(record, key):
                setattr(record, key, "")
        return True


class TextFormatter(logging.Formatter):
    def __init__(self) -> None:
        super().__init__(
            "%(asctime)s %(levelname)s %(name)s "
            "request_id=%(request_id)s turn_id=%(turn_id)s: %(message)s"
        )

    def format(self, record: logging.LogRecord) -> str:
        return redact_text(super().format(record))


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        for key in FIELD_KEYS:
            value = getattr(record, key, None)
            if value not in (None, ""):
                payload[key] = value
        return redact_text(json.dumps(payload, ensure_ascii=False, default=str))


def log_event(event: str, **fields: Any) -> None:
    extra = {key: value for key, value in fields.items() if value not in (None, "")}
    extra["event"] = event
    request_id = extra.get("request_id") or snapshot()["request_id"] or "-"
    turn_id = extra.get("turn_id") or snapshot()["turn_id"] or "-"
    extra.setdefault("request_id", request_id)
    extra.setdefault("turn_id", turn_id)
    log.info("%s request_id=%s turn_id=%s", event, request_id, turn_id, extra=extra)


def log_tool(
    name: str,
    result: dict[str, Any] | None,
    *,
    latency_ms: int,
    runtime: str | None = None,
    bot_id: str | None = None,
    turn_id: str | None = None,
    thread_id: str | None = None,
) -> None:
    extra: dict[str, Any] = {
        "event": "tool",
        "tool": name,
        "latency_ms": int(latency_ms),
        "result": tool_result_summary(result),
    }
    if runtime:
        extra["runtime"] = runtime
    if bot_id:
        extra["bot_id"] = bot_id
    if thread_id:
        extra["thread_id"] = thread_id
    if turn_id:
        extra["turn_id"] = turn_id
        extra.setdefault("request_id", request_id_for_turn(turn_id) or current_request_id())
    request_id = extra.get("request_id") or snapshot()["request_id"] or "-"
    extra.setdefault("request_id", request_id)
    log.info(
        "tool %s result=%s request_id=%s turn_id=%s",
        name,
        extra["result"],
        request_id,
        turn_id or extra.get("turn_id") or "-",
        extra=extra,
    )


class RequestContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        request_id = accept_request_id(request.headers.get("x-request-id"))
        token = bind_request(request_id)
        started = time.monotonic()
        status = 500
        try:
            response = await call_next(request)
            status = response.status_code
            response.headers["X-Request-Id"] = request_id
            return response
        finally:
            path = request.url.path
            if path not in _SKIP_HTTP_PATHS:
                safe_path = "/novnc/[redacted]" if path.startswith("/novnc") else path
                latency_ms = int((time.monotonic() - started) * 1000)
                log.info(
                    "%s %s %s %sms request_id=%s",
                    request.method,
                    safe_path,
                    status,
                    latency_ms,
                    request_id,
                    extra={
                        "event": "http",
                        "method": request.method,
                        "path": safe_path,
                        "status": status,
                        "latency_ms": latency_ms,
                    },
                )
            reset_request(token)


def configure_logging(*, log_format: str | None = None, force: bool = False) -> None:
    root = logging.getLogger()
    if root.handlers and not force:
        return
    chosen = resolved_log_format(log_format)
    handler = logging.StreamHandler()
    handler.addFilter(ContextFilter())
    handler.setFormatter(JsonFormatter() if chosen == "json" else TextFormatter())
    logging.basicConfig(level=logging.INFO, handlers=[handler], force=True)
    logging.getLogger("uvicorn.access").addFilter(ContextFilter())
