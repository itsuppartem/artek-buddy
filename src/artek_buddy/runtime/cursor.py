from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

from cursor_sdk import (
    AgentBusyError,
    AgentOptions,
    AsyncClient,
    CursorAgentError,
    CustomTool,
    LocalAgentOptions,
    ModelParameterValue,
    ModelSelection,
)

from artek_buddy.config import Settings
from artek_buddy.runtime.base import RuntimeBase
from artek_buddy.runtime.cursor_wait import (
    dead_wait_owner_error,
    describe_cursor_wait,
    log_cursor_wait,
    note_auth_failures,
    send_local_options,
    should_retry_dead_wait,
)
from artek_buddy.runtime.tools import ProductTools
from artek_buddy.runtime.types import AgentRuntimeError, ProductStreamEvent, RunRecord
from artek_buddy.stream import map_cursor_event

log = logging.getLogger("artek_buddy")


@dataclass
class _SendAttempt:
    run: Any
    agent_id: str
    streamed: int
    events: list[ProductStreamEvent]
    mapped: str
    text: str | None
    error: str | None
    duration_s: float


async def _cancel_cursor_run(run: Any) -> None:
    if run is None:
        return
    for name in ("cancel", "stop", "abort"):
        fn = getattr(run, name, None)
        if not callable(fn):
            continue
        try:
            result = fn()
            if asyncio.iscoroutine(result):
                await result
        except Exception:
            log.exception("cursor run %s failed", name)
        return


def build_model(
    settings: Settings,
    model_id: str | None = None,
    effort: str | None = None,
    fast: bool | None = None,
) -> ModelSelection:
    params: list[ModelParameterValue] = []
    effort_value = effort if effort else settings.cursor_model_effort
    use_fast = settings.cursor_model_fast if fast is None else fast
    if effort_value:
        params.append(ModelParameterValue(id="effort", value=effort_value))
    if use_fast:
        params.append(ModelParameterValue(id="fast", value="true"))
    return ModelSelection(id=model_id or settings.cursor_model, params=params)


class CursorRuntime(RuntimeBase):
    def __init__(
        self,
        client: AsyncClient,
        settings: Settings,
        store: Any | None = None,
        computers: Any | None = None,
    ) -> None:
        super().__init__(settings, store=store, computers=computers)
        self.client = client
        self._locks: dict[str, asyncio.Lock] = {}
        self._auth_fails = 0
        self.bridge_recycles = 0

    def model_selection(self) -> ModelSelection:
        model_id = self.settings.cursor_model
        effort = None
        fast = None
        if self.store is not None:
            try:
                default = self.store.get_default_model()
                effort, fast = self.store.get_model_params()
            except Exception:
                default = None
            if default and default[0] == "cursor" and default[1]:
                model_id = default[1]
        return build_model(self.settings, model_id, effort=effort, fast=fast)

    @property
    def model(self) -> ModelSelection:
        return self.model_selection()

    def _custom_tools(self, bot_id: str | None = None, role: str = "lead") -> dict[str, CustomTool]:
        registry = ProductTools(self)
        tools: dict[str, CustomTool] = {}
        for spec in registry.specs(role):

            def execute(
                args: dict[str, Any],
                context: Any,
                *,
                name: str = spec.name,
            ) -> dict[str, Any]:
                return registry.execute(name, args, bound_bot_id=bot_id)

            tools[spec.name] = CustomTool(
                execute=execute,
                description=spec.description,
                input_schema=spec.input_schema,
            )
        return tools

    def _local(self, bot_id: str | None = None, role: str = "lead") -> LocalAgentOptions:
        return LocalAgentOptions(
            cwd=self.home_cwd(bot_id),
            custom_tools=self._custom_tools(bot_id, role=role),
        )

    def _agent_options(self, bot_id: str | None = None, role: str = "lead") -> AgentOptions:
        # resume() JSON-encodes options. A raw dict with a live
        # LocalAgentOptions is not serializable; AgentOptions.to_json() is.
        return AgentOptions(
            api_key=self.settings.cursor_api_key,
            model=self.model,
            local=self._local(bot_id, role=role),
        )

    async def start(self) -> None:
        self._ensure_dirs()
        models = await self.client.models.list()
        ids = [model.id for model in models]
        log.info("catalog models: %s", ", ".join(ids))
        if self.store is not None:
            try:
                self.store.replace_catalog("cursor", ids)
            except Exception:
                log.exception("failed to persist Cursor catalog")
        if self.settings.cursor_model not in ids:
            raise AgentRuntimeError(
                f"model {self.settings.cursor_model!r} is not available for this key: {ids}"
            )
        saved = self._load_state()
        live = await self.ensure_session(saved, name="artek-buddy")
        self.default_agent_id = live
        self._save_state(live)

    async def create_session(
        self,
        name: str = "artek-buddy",
        persist_default: bool = False,
        bot_id: str | None = None,
        role: str = "lead",
    ) -> str:
        agent = await self.client.agents.create(
            model=self.model,
            api_key=self.settings.cursor_api_key,
            name=name,
            local=self._local(bot_id, role=role),
        )
        self._agents[agent.agent_id] = agent
        self._locks[agent.agent_id] = asyncio.Lock()
        self.bind_agent_bot(agent.agent_id, bot_id)
        if persist_default or self.default_agent_id is None:
            self.default_agent_id = agent.agent_id
            self._save_state(agent.agent_id)
        log.info("created agent %s", agent.agent_id)
        return agent.agent_id

    async def ensure_session(
        self,
        agent_id: str | None,
        name: str = "artek-buddy",
        bot_id: str | None = None,
        role: str = "lead",
    ) -> str:
        if agent_id and agent_id in self._agents:
            return agent_id
        if agent_id:
            try:
                agent = await self.client.agents.resume(
                    agent_id, self._agent_options(bot_id, role=role)
                )
                live_id = agent.agent_id or agent_id
                self._agents[live_id] = agent
                self._locks.setdefault(live_id, asyncio.Lock())
                self.bind_agent_bot(live_id, bot_id)
                log.info("resumed agent %s", live_id)
                return live_id
            except Exception:
                log.exception("resume failed, creating a new agent")
        elif self.default_agent_id:
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

    async def _agent(
        self,
        session_id: str | None = None,
        bot_id: str | None = None,
        role: str = "lead",
    ) -> tuple[str, Any, asyncio.Lock]:
        agent_id = await self.ensure_session(session_id, bot_id=bot_id, role=role)
        self.bind_agent_bot(agent_id, bot_id)
        agent = self._agents.get(agent_id)
        if agent is None:
            raise AgentRuntimeError("no agent session")
        lock = self._locks.setdefault(agent_id, asyncio.Lock())
        return agent_id, agent, lock

    async def _close_agent(self, agent: Any) -> None:
        close = getattr(agent, "close", None)
        if not callable(close):
            return
        try:
            result = close()
            if asyncio.iscoroutine(result):
                await result
        except Exception:
            log.exception("failed to close cursor agent")

    async def _cancel_stale_runs(self, agent_id: str) -> None:
        list_runs = getattr(self.client, "list_runs", None)
        cancel_run = getattr(self.client, "cancel_run", None)
        if not callable(list_runs) or not callable(cancel_run):
            return
        try:
            listed = await list_runs(agent_id, limit=8)
        except Exception:
            log.exception("failed to list cursor runs for %s", agent_id)
            return
        items = getattr(listed, "items", None)
        if items is None:
            items = []
        for run in items:
            status = str(
                getattr(run, "status", "")
                or getattr(getattr(run, "snapshot", None), "status", "")
                or ""
            ).lower()
            if "running" not in status:
                continue
            rid = getattr(run, "id", None) or getattr(run, "run_id", None)
            if not rid:
                continue
            try:
                await cancel_run(str(rid), agent_id=agent_id)
                log.warning("cancelled stale cursor run %s on %s", rid, agent_id)
            except Exception:
                log.exception("failed to cancel stale cursor run %s", rid)

    async def _recycle_dead_agent(self, burned_id: str, bot_id: str | None) -> str:
        log.warning("recycling cursor agent %s", burned_id)
        burned = self._agents.pop(burned_id, None)
        self._locks.pop(burned_id, None)
        if burned is not None:
            await self._close_agent(burned)
        self._auth_fails = 0
        self.bridge_recycles += 1
        live = await self.create_session(
            name="artek-buddy",
            persist_default=True,
            bot_id=bot_id,
            role="lead",
        )
        if bot_id and self.store is not None and hasattr(self.store, "attach_agent"):
            try:
                self.store.attach_agent(bot_id, live)
            except Exception:
                log.exception("failed to attach recycled agent")
        return live

    async def _attempt_send(
        self,
        agent: Any,
        agent_id: str,
        prompt: str,
        cwd: str,
        *,
        force: bool,
    ) -> _SendAttempt:
        events: list[ProductStreamEvent] = []
        streamed = 0
        run = await agent.send(prompt, send_local_options(cwd, force=force))
        log.info("run started run_id=%s agent_id=%s force=%s", run.id, agent_id, force)
        async for event in run.events():
            mapped_events = map_cursor_event(event)
            if mapped_events:
                streamed += 1
            for typ, payload in mapped_events:
                events.append(ProductStreamEvent(type=typ, payload=payload))
        text = ""
        status = "unknown"
        waited = time.monotonic()
        result = None
        try:
            result = await run.wait()
            text = getattr(result, "result", None) or ""
            status = str(getattr(result, "status", "unknown"))
        except Exception:
            log.exception("wait after stream failed")
        duration_s = time.monotonic() - waited
        if not text:
            try:
                text = await run.text()
            except Exception:
                text = ""
        mapped, wait_text, wait_error = describe_cursor_wait(result, run)
        if wait_text:
            text = wait_text
        log_cursor_wait(
            str(getattr(run, "id", "")),
            agent_id,
            status,
            duration_s,
            wait_error,
        )
        return _SendAttempt(
            run=run,
            agent_id=agent_id,
            streamed=streamed,
            events=events,
            mapped=mapped,
            text=text or None,
            error=wait_error,
            duration_s=duration_s,
        )

    async def stream(
        self,
        prompt: str,
        session_id: str | None = None,
        bot_id: str | None = None,
        role: str = "lead",
    ) -> AsyncIterator[ProductStreamEvent | RunRecord]:
        agent_id, agent, lock = await self._agent(session_id, bot_id=bot_id, role=role)
        cwd = self.home_cwd(bot_id or self.resolve_turn_context()[0])
        self.last_prompt = prompt
        async with lock:
            run = None
            force = False
            forced_once = False
            recycled_once = False
            try:
                while True:
                    await self._cancel_stale_runs(agent_id)
                    try:
                        attempt = await self._attempt_send(
                            agent, agent_id, prompt, cwd, force=force
                        )
                    except AgentBusyError:
                        if forced_once:
                            raise
                        log.warning(
                            "cursor agent busy; retrying send with force on %s",
                            agent_id,
                        )
                        force = True
                        forced_once = True
                        continue
                    run = attempt.run
                    for event in attempt.events:
                        yield event
                    self._auth_fails, recycle = note_auth_failures(
                        self._auth_fails,
                        status=attempt.mapped,
                        error=attempt.error,
                        duration_s=attempt.duration_s,
                    )
                    if attempt.mapped == "completed":
                        yield RunRecord(
                            id=str(getattr(attempt.run, "id", "")),
                            agent_id=agent_id,
                            status=attempt.mapped,
                            result=attempt.text,
                            error=None,
                        )
                        return
                    retry_dead = should_retry_dead_wait(
                        streamed=attempt.streamed,
                        status=attempt.mapped,
                        error=attempt.error,
                        duration_s=attempt.duration_s,
                    )
                    if retry_dead and not forced_once:
                        log.warning(
                            "dead cursor wait; retrying same send with force on %s",
                            agent_id,
                        )
                        force = True
                        forced_once = True
                        continue
                    if retry_dead and forced_once and not recycled_once:
                        agent_id = await self._recycle_dead_agent(agent_id, bot_id)
                        agent = self._agents[agent_id]
                        force = False
                        recycled_once = True
                        continue
                    if recycle and not recycled_once:
                        await self._recycle_dead_agent(agent_id, bot_id)
                        recycled_once = True
                    error_code = dead_wait_owner_error(attempt.error, recycle or recycled_once)
                    yield RunRecord(
                        id=str(getattr(attempt.run, "id", "")),
                        agent_id=agent_id,
                        status=attempt.mapped,
                        result=attempt.text,
                        error=error_code,
                    )
                    return
            except CursorAgentError as err:
                log.error(
                    "run did not start: %s retryable=%s request_id=%s",
                    err.message,
                    err.is_retryable,
                    getattr(err, "request_id", None),
                )
                raise AgentRuntimeError(
                    err.message,
                    retryable=bool(err.is_retryable),
                    request_id=getattr(err, "request_id", None),
                ) from err
            except asyncio.CancelledError:
                await _cancel_cursor_run(run)
                raise

    async def list_models(self) -> list[dict[str, Any]]:
        models = await self.client.models.list()
        payload: list[dict[str, Any]] = []
        for model in models:
            item: dict[str, Any] = {"id": model.id}
            variants = getattr(model, "variants", None)
            if variants:
                item["variants"] = [
                    getattr(variant, "id", None) or str(variant) for variant in variants
                ]
            payload.append(item)
        return payload
