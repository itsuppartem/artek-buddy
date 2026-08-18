from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any

from artek_buddy.config import Settings
from artek_buddy.db.shaping import new_id
from artek_buddy.runtime.base import RuntimeBase
from artek_buddy.runtime.tools import ProductTools
from artek_buddy.runtime.types import AgentRuntimeError, ProductStreamEvent, RunRecord
from artek_buddy.stream import _map_tool_to_events

log = logging.getLogger("artek_buddy")


@dataclass
class ScriptedStep:
    event: tuple[str, dict[str, Any]] | None = None
    tool: str | None = None
    args: dict[str, Any] = field(default_factory=dict)
    result: str | None = None
    status: str | None = None
    error: str | None = None
    raise_error: str | None = None


def scripted_text(text: str) -> ScriptedStep:
    return ScriptedStep(event=("thread.message.updated", {"text": text, "kind": "text", "replace": True}))


def scripted_progress(text: str, kind: str = "thinking") -> ScriptedStep:
    return ScriptedStep(event=("thread.progress", {"text": text, "kind": kind, "replace": True}))


def scripted_tool(name: str, **args: Any) -> ScriptedStep:
    return ScriptedStep(tool=name, args=dict(args))


def scripted_finish(result: str = "ok", status: str = "completed", error: str | None = None) -> ScriptedStep:
    return ScriptedStep(result=result, status=status, error=error)


class ScriptedRuntime(RuntimeBase):
    def __init__(
        self,
        settings: Settings,
        store: Any | None = None,
        computers: Any | None = None,
    ) -> None:
        super().__init__(settings, store=store, computers=computers)
        self._queue: list[list[ScriptedStep]] = []
        self._seq = 0
        self.last_tool_results: list[tuple[str, dict[str, Any]]] = []

    def queue_turn(self, *steps: ScriptedStep) -> None:
        self._queue.append(list(steps))

    async def start(self) -> None:
        self._ensure_dirs()
        saved = self._load_state()
        live = await self.ensure_session(saved, name="artek-buddy")
        self.default_agent_id = live
        self._save_state(live)
        log.info("scripted runtime ready default_agent=%s", live)

    async def create_session(
        self,
        name: str = "artek-buddy",
        persist_default: bool = False,
        bot_id: str | None = None,
        role: str = "lead",
    ) -> str:
        self._seq += 1
        agent_id = f"sa-{self._seq}"
        self._agents[agent_id] = {"name": name, "role": role}
        self.bind_agent_bot(agent_id, bot_id)
        if persist_default or self.default_agent_id is None:
            self.default_agent_id = agent_id
            self._save_state(agent_id)
        log.info("created scripted agent %s", agent_id)
        return agent_id

    async def ensure_session(
        self,
        agent_id: str | None,
        name: str = "artek-buddy",
        bot_id: str | None = None,
        role: str = "lead",
    ) -> str:
        if agent_id and agent_id in self._agents:
            self.bind_agent_bot(agent_id, bot_id)
            return agent_id
        if agent_id:
            self._agents[agent_id] = {"name": name, "role": role}
            self.bind_agent_bot(agent_id, bot_id)
            if self.default_agent_id is None:
                self.default_agent_id = agent_id
                self._save_state(agent_id)
            return agent_id
        if self.default_agent_id:
            return await self.ensure_session(
                self.default_agent_id,
                name=name,
                bot_id=bot_id,
                role=role,
            )
        return await self.create_session(
            name=name,
            persist_default=self.default_agent_id is None,
            bot_id=bot_id,
            role=role,
        )

    async def stream(
        self,
        prompt: str,
        session_id: str | None = None,
        bot_id: str | None = None,
        role: str = "lead",
    ) -> AsyncIterator[ProductStreamEvent | RunRecord]:
        agent_id = await self.ensure_session(session_id, bot_id=bot_id, role=role)
        self.bind_agent_bot(agent_id, bot_id)
        steps = self._queue.pop(0) if self._queue else [
            scripted_text("ok"),
            scripted_finish("ok"),
        ]
        tools = ProductTools(self)
        result = ""
        status = "completed"
        error: str | None = None
        run_id = new_id("run")
        for step in steps:
            if step.raise_error:
                raise AgentRuntimeError(step.raise_error)
            if step.tool:
                tool_result = tools.execute(step.tool, step.args, bound_bot_id=bot_id)
                self.last_tool_results.append((step.tool, tool_result))
                for typ, payload in _map_tool_to_events(step.tool, step.tool, step.args, "completed"):
                    yield ProductStreamEvent(type=typ, payload=payload)
                continue
            if step.event:
                yield ProductStreamEvent(type=step.event[0], payload=step.event[1])
                if step.event[0] == "thread.message.updated":
                    text = str(step.event[1].get("text") or "")
                    if text:
                        result = text
                continue
            if step.status or step.result is not None:
                status = step.status or "completed"
                result = step.result if step.result is not None else result
                error = step.error
        yield RunRecord(
            id=run_id,
            agent_id=agent_id,
            status=status,
            result=result or None,
            error=error,
        )

    async def list_models(self) -> list[dict[str, Any]]:
        model_id = self.settings.cursor_model or "scripted"
        return [{"id": model_id}]
