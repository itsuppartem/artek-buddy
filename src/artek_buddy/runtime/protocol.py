from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any, Protocol, runtime_checkable

from artek_buddy.config import Settings
from artek_buddy.runtime.types import ProductStreamEvent, RunRecord


@runtime_checkable
class AgentRuntime(Protocol):
    settings: Settings
    store: Any
    computers: Any
    default_agent_id: str | None
    memory: Any
    subagents: Any
    events: Any
    loop: Any
    on_takeover_requested: Any

    def bind_agent_bot(self, agent_id: str | None, bot_id: str | None) -> None: ...

    def mark_session_fresh(self, agent_id: str | None) -> None: ...

    def consume_session_fresh(self, agent_id: str | None) -> bool: ...

    def build_session_resume(self, bot_id: str | None) -> str | None: ...

    def set_current_turn_context(
        self,
        bot_id: str | None,
        run_id: str | None,
        thread_id: str | None,
        agent_id: str | None = None,
        role: str = "lead",
        device_id: str | None = None,
    ) -> Any: ...

    def has_sent_message_in_turn(self, run_id: str | None) -> bool: ...

    def has_sent_terminal_message_in_turn(self, run_id: str | None) -> bool: ...

    def mark_message_sent(self, run_id: str | None, *, terminal: bool = False) -> None: ...

    def clear_active_turn(self, bot_id: str | None = None, run_id: str | None = None) -> None: ...

    def resolve_turn_context(
        self,
        bound_bot_id: str | None = None,
    ) -> tuple[str | None, str | None, str | None]: ...

    def resolve_turn_role(self, bound_bot_id: str | None = None) -> str: ...

    def home_cwd(self, bot_id: str | None = None) -> str: ...

    async def start(self) -> None: ...

    async def create_session(
        self,
        name: str = "artek-buddy",
        persist_default: bool = False,
        bot_id: str | None = None,
        role: str = "lead",
    ) -> str: ...

    async def ensure_session(
        self,
        agent_id: str | None,
        name: str = "artek-buddy",
        bot_id: str | None = None,
        role: str = "lead",
    ) -> str: ...

    def stream(
        self,
        prompt: str,
        session_id: str | None = None,
        bot_id: str | None = None,
        role: str = "lead",
    ) -> AsyncIterator[ProductStreamEvent | RunRecord]: ...

    async def send(self, prompt: str, session_id: str | None = None) -> RunRecord: ...

    async def list_models(self) -> list[dict[str, Any]]: ...
