from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

TurnRole = Literal["lead", "subagent"]
ActivityKind = Literal["run_started", "tool_started", "tool_finished", "text", "clarification"]


@dataclass(frozen=True)
class TurnContext:
    bot_id: str
    run_id: str
    thread_id: str
    role: TurnRole = "lead"
    agent_id: str | None = None
    device_id: str | None = None


@dataclass
class ToolTurnBox:
    agent_id: str | None = None
    turn: TurnContext | None = None


@dataclass
class RunRecord:
    id: str
    agent_id: str
    status: str
    result: str | None = None
    error: str | None = None


@dataclass(frozen=True)
class ProductStreamEvent:
    type: str
    payload: dict[str, Any] = field(default_factory=dict)


ErrorCategory = Literal[
    "unavailable",
    "timeout",
    "cancelled",
    "exhausted",
    "transient",
    "permanent",
]
TRANSIENT_CATEGORIES: set[str] = {"unavailable", "timeout", "transient"}


class AgentRuntimeError(Exception):
    def __init__(
        self,
        message: str,
        *,
        category: str = "permanent",
        retryable: bool = False,
        request_id: str | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.category = category
        self.retryable = retryable or category in TRANSIENT_CATEGORIES
        self.request_id = request_id

    @property
    def is_transient(self) -> bool:
        return self.category in TRANSIENT_CATEGORIES

    @property
    def safe_message(self) -> str:
        from artek_buddy.observe import redact_text

        return redact_text(self.message)


class AgentRuntimeUnavailable(AgentRuntimeError):
    def __init__(self, message: str, *, request_id: str | None = None) -> None:
        super().__init__(message, category="unavailable", retryable=True, request_id=request_id)


class AgentRuntimeTimeout(AgentRuntimeError):
    def __init__(self, message: str, *, request_id: str | None = None) -> None:
        super().__init__(message, category="timeout", retryable=True, request_id=request_id)


class AgentRuntimeCancelled(AgentRuntimeError):
    def __init__(
        self, message: str = "run was cancelled", *, request_id: str | None = None
    ) -> None:
        super().__init__(message, category="cancelled", retryable=False, request_id=request_id)


class AgentRuntimeExhausted(AgentRuntimeError):
    def __init__(self, message: str, *, request_id: str | None = None) -> None:
        super().__init__(message, category="exhausted", retryable=True, request_id=request_id)
