from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


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


class AgentRuntimeError(Exception):
    def __init__(
        self,
        message: str,
        *,
        retryable: bool = False,
        request_id: str | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.retryable = retryable
        self.request_id = request_id
