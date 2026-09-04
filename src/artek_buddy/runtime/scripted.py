from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

from artek_buddy.config import Settings
from artek_buddy.db.shaping import TURN_FAILED, new_id
from artek_buddy.runtime.base import RuntimeBase
from artek_buddy.runtime.cursor_wait import dead_wait_owner_error, note_auth_failures
from artek_buddy.runtime.scripted_scenarios import (
    E2E_AUTH_ERROR,
    ScriptedStep,
    _materialize_blocks,
    _user_tail,
    steps_for_prompt,
)
from artek_buddy.runtime.tools import ProductTools
from artek_buddy.runtime.types import AgentRuntimeError, ProductStreamEvent, RunRecord
from artek_buddy.stream import _map_tool_to_events

log = logging.getLogger("artek_buddy")


def __getattr__(name: str) -> Any:
    from artek_buddy.runtime import scripted_scenarios as scenarios

    if hasattr(scenarios, name):
        return getattr(scenarios, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


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
        self._auth_fails = 0
        self.bridge_recycles = 0
        self._pending_recover = False
        self._skill_fixture: Any | None = None

    def queue_turn(self, *steps: ScriptedStep) -> None:
        self._queue.append(list(steps))

    async def start(self) -> None:
        from artek_buddy.book_fetch import start_skill_fixture
        from artek_buddy.runtime import scripted_scenarios as scenarios

        self._ensure_dirs()
        self._skill_fixture = start_skill_fixture()
        scenarios.E2E_BOOK_URL = self._skill_fixture.url
        self.book_fixture_url = self._skill_fixture.url
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
        if role == "lead":
            self.mark_session_fresh(agent_id)
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
        if self.session_foreign_to_bot(agent_id, bot_id):
            return await self.create_session(
                name=name,
                persist_default=False,
                bot_id=bot_id,
                role=role,
            )
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
        return await self.create_session(
            name=name,
            persist_default=self.default_agent_id is None,
            bot_id=bot_id,
            role=role,
        )

    async def _recycle_scripted_agent(self, agent_id: str, bot_id: str | None) -> str:
        self._agents.pop(agent_id, None)
        live = await self.create_session(
            name="artek-buddy",
            persist_default=True,
            bot_id=bot_id,
        )
        if bot_id and self.store is not None:
            try:
                self.store.attach_agent(bot_id, live)
            except Exception:
                log.exception("failed to attach recycled scripted agent")
        self.bridge_recycles += 1
        self._auth_fails = 0
        return live

    async def stream(
        self,
        prompt: str,
        session_id: str | None = None,
        bot_id: str | None = None,
        role: str = "lead",
    ) -> AsyncIterator[ProductStreamEvent | RunRecord]:
        agent_id = await self.ensure_session(session_id, bot_id=bot_id, role=role)
        self.bind_agent_bot(agent_id, bot_id)
        self.last_prompt = prompt
        self.last_tool_results = []
        hay = _user_tail(prompt).lower()
        if "e2e-dead-wait-stuck" in hay:
            run_id = new_id("run")
            self._auth_fails, recycle = note_auth_failures(
                self._auth_fails,
                status="failed",
                error=TURN_FAILED,
                duration_s=0.0,
            )
            if recycle:
                agent_id = await self._recycle_scripted_agent(agent_id, bot_id)
            yield RunRecord(
                id=run_id,
                agent_id=agent_id,
                status="failed",
                result=None,
                error=dead_wait_owner_error(TURN_FAILED, True),
            )
            return
        if "e2e-dead-wait" in hay:
            run_id = new_id("run")
            self._auth_fails, recycle = note_auth_failures(
                self._auth_fails,
                status="failed",
                error=TURN_FAILED,
                duration_s=0.0,
            )
            if recycle:
                agent_id = await self._recycle_scripted_agent(agent_id, bot_id)
            yield RunRecord(
                id=run_id,
                agent_id=agent_id,
                status="completed",
                result="ok",
                error=None,
            )
            return
        if "e2e-auth-error" in hay:
            run_id = new_id("run")
            if self._pending_recover:
                self._pending_recover = False
                self._auth_fails = 0
                yield RunRecord(
                    id=run_id,
                    agent_id=agent_id,
                    status="completed",
                    result="recovered",
                    error=None,
                )
                return
            self._auth_fails, recycle = note_auth_failures(
                self._auth_fails,
                status="failed",
                error=E2E_AUTH_ERROR,
                duration_s=0.01,
            )
            yield RunRecord(
                id=run_id,
                agent_id=agent_id,
                status="failed",
                result=None,
                error=E2E_AUTH_ERROR,
            )
            if recycle:
                await self._recycle_scripted_agent(agent_id, bot_id)
                self._pending_recover = True
            return
        steps = self._queue.pop(0) if self._queue else steps_for_prompt(prompt)
        tools = ProductTools(self)
        result = ""
        status = "completed"
        error: str | None = None
        run_id = new_id("run")
        for step in steps:
            if step.delay_s:
                try:
                    await asyncio.sleep(step.delay_s)
                except asyncio.CancelledError:
                    if not step.ignore_cancel:
                        raise
                continue
            if step.write_home:
                name, data = step.write_home
                home = Path(self.home_cwd(bot_id))
                home.mkdir(parents=True, exist_ok=True)
                (home / Path(name).name).write_bytes(data)
                continue
            if step.owner_auto_path:
                hub = getattr(self, "consent", None)
                if hub is not None:
                    ctx_bot, ctx_run, _thread = self.resolve_turn_context(bot_id)
                    request_id = hub.start_auto_owner_read(
                        bot_id=ctx_bot or bot_id or "",
                        path=step.owner_auto_path or "",
                        run_id=ctx_run,
                        device_id=None,
                    )
                    if request_id:
                        await asyncio.sleep(0)
                        await asyncio.to_thread(hub.take_owner_file, request_id)
                    if ctx_run:
                        try:
                            self.store.mark_run_running(ctx_run)
                        except Exception:
                            log.exception("failed to resume run after owner file")
                continue
            if step.raise_error:
                raise AgentRuntimeError(step.raise_error)
            if step.consent:
                hub = getattr(self, "consent", None)
                if hub is not None:
                    ctx_bot, ctx_run, _thread = self.resolve_turn_context(bot_id)
                    request_id = hub.offer(
                        bot_id=ctx_bot or bot_id or "",
                        action_class=str(step.consent.get("action_class") or ""),
                        scope_key=str(step.consent.get("scope_key") or "*"),
                        summary=str(step.consent.get("summary") or "Allow this?"),
                        run_id=ctx_run,
                        detail=step.consent.get("detail"),
                        path=step.consent.get("path"),
                        job=step.consent.get("job"),
                    )
                    if request_id:
                        decision = await asyncio.to_thread(hub.wait_decision, request_id)
                        if ctx_run:
                            try:
                                self.store.mark_run_running(ctx_run)
                            except Exception:
                                log.exception("failed to resume run after consent")
                        if decision not in {"once", "always"}:
                            status = "failed"
                            error = "denied"
                            break
                continue
            if step.blocks:
                posted = tools._append_bot_blocks(
                    {},
                    bot_id,
                    _materialize_blocks(self.store, step.blocks, bot_id),
                )
                if not posted.get("ok"):
                    raise AgentRuntimeError(str(posted.get("error") or "could not append blocks"))
                await asyncio.sleep(0)
                continue
            if step.tool:
                if step.tool == "ask_user":
                    tool_result = await asyncio.to_thread(
                        tools.execute,
                        step.tool,
                        step.args,
                        bound_bot_id=bot_id,
                    )
                else:
                    tool_result = tools.execute(step.tool, step.args, bound_bot_id=bot_id)
                self.last_tool_results.append((step.tool, tool_result))
                if step.require_ok and (
                    not isinstance(tool_result, dict) or not tool_result.get("ok")
                ):
                    status = "failed"
                    error = str(
                        (tool_result or {}).get("error")
                        if isinstance(tool_result, dict)
                        else "tool failed"
                    )
                    break
                for typ, payload in _map_tool_to_events(
                    step.tool, step.tool, step.args, "completed"
                ):
                    yield ProductStreamEvent(type=typ, payload=payload)
                spoken = tool_result.get("text") if tool_result.get("announce") else None
                if spoken:
                    result = str(spoken)
                    yield ProductStreamEvent(
                        type="thread.message.updated",
                        payload={"text": result, "kind": "text", "replace": True},
                    )
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
                if "e2e-worker-block" in hay:
                    notes = [hay]
                    for _name, tool_result in self.last_tool_results:
                        if isinstance(tool_result, dict):
                            notes.append(str(tool_result.get("lead_clarification") or ""))
                    if "path b" in "\n".join(notes).lower():
                        result = "path B done"
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
