from __future__ import annotations

import asyncio
import logging
from typing import Any

from artek_buddy.bus import EventHub
from artek_buddy.contracts.domain import Bot, Subagent
from artek_buddy.contracts.events import ProductEvent, ProductEventType
from artek_buddy.db.history import HistoryStore
from artek_buddy.db.shaping import isoformat_utc, new_id
from artek_buddy.memory import format_memory_context, wrap_turn_prompt
from artek_buddy.runtime import AgentRuntime, ProductStreamEvent, RunRecord
from artek_buddy.stream import accumulate

log = logging.getLogger("artek_buddy")

MAX_SUBAGENTS = 4


class SubagentError(Exception):
    pass


class SubagentService:
    def __init__(self, store: HistoryStore, runtime: AgentRuntime) -> None:
        self.store = store
        self.runtime = runtime
        self.events: EventHub | None = None
        self.loop: asyncio.AbstractEventLoop | None = None
        self.tasks: dict[str, asyncio.Task[Any]] = {}

    def bind(self, events: EventHub, loop: asyncio.AbstractEventLoop) -> None:
        self.events = events
        self.loop = loop

    def spawn(self, bot: Bot, name: str, task: str, parent_run_id: str | None = None) -> Subagent:
        task_text = (task or "").strip()
        if not task_text:
            raise SubagentError("task cannot be empty")
        if self.store.running_subagent_count(bot.id) >= MAX_SUBAGENTS:
            raise SubagentError("too many subagents are already running")
        record = self.store.create_subagent(
            bot, name=name, task=task_text, parent_run_id=parent_run_id
        )
        self._emit(bot, record)
        self._schedule(record.id, self._run(bot, record.id, mode="start"))
        return record

    def inspect(self, bot: Bot, ref: str) -> Subagent:
        found = self.store.resolve_subagent(bot.id, ref)
        if found is None:
            raise SubagentError("subagent not found")
        return found

    def list_for(self, bot: Bot) -> list[Subagent]:
        return self.store.list_subagents(bot.id)

    def stop(self, bot: Bot, ref: str) -> Subagent:
        found = self.inspect(bot, ref)
        task = self.tasks.get(found.id)
        if task and not task.done():
            task.cancel()
        updated = self.store.update_subagent(found.id, status="cancelled", error="stopped")
        if updated is None:
            raise SubagentError("subagent not found")
        self._emit(bot, updated)
        return updated

    def restart(self, bot: Bot, ref: str) -> Subagent:
        found = self.inspect(bot, ref)
        task = self.tasks.get(found.id)
        if task and not task.done():
            task.cancel()
        updated = self.store.update_subagent(found.id, status="queued", clear_output=True)
        if updated is None:
            raise SubagentError("subagent not found")
        self._emit(bot, updated)
        self._schedule(updated.id, self._run(bot, updated.id, mode="restart"))
        return updated

    def steer(self, bot: Bot, ref: str, text: str) -> Subagent:
        note = (text or "").strip()
        if not note:
            raise SubagentError("clarification cannot be empty")
        found = self.inspect(bot, ref)
        if found.status not in {"queued", "running"}:
            if self.store.running_subagent_count(bot.id) >= MAX_SUBAGENTS:
                raise SubagentError("too many subagents are already running")
        updated = self.store.append_clarification(found.id, note)
        if updated is None:
            raise SubagentError("subagent not found")
        queued = self.store.update_subagent(updated.id, status="queued") or updated
        self._emit(bot, queued)
        self._schedule(queued.id, self._run(bot, queued.id, mode="steer"))
        return queued

    def stop_all(self, bot: Bot) -> None:
        for item in self.store.list_subagents(bot.id):
            if item.status in {"queued", "running"}:
                try:
                    self.stop(bot, item.id)
                except SubagentError:
                    continue

    def _schedule(self, sub_id: str, coro: Any) -> None:
        loop = self.loop
        if loop is None:
            raise SubagentError("subagent service is not bound")

        def starter() -> None:
            previous = self.tasks.get(sub_id)
            if previous and not previous.done():
                previous.cancel()
            task = loop.create_task(coro, name=f"subagent-{sub_id}")
            self.tasks[sub_id] = task

            def _drop(done: asyncio.Task[Any]) -> None:
                if self.tasks.get(sub_id) is done:
                    self.tasks.pop(sub_id, None)

            task.add_done_callback(_drop)

        loop.call_soon_threadsafe(starter)

    async def _run(self, bot: Bot, sub_id: str, mode: str = "start") -> None:
        record = self.store.get_subagent(sub_id)
        if record is None:
            return
        live = bot
        try:
            session_id = (
                record.cursor_agent_id if mode == "steer" and record.cursor_agent_id else None
            )
            if not session_id:
                session_id = await self.runtime.create_session(
                    name=record.name,
                    persist_default=False,
                    bot_id=live.id,
                    role="subagent",
                )
            self.runtime.bind_agent_bot(session_id, live.id)
            record = (
                self.store.update_subagent(
                    sub_id,
                    status="running",
                    cursor_agent_id=session_id,
                )
                or record
            )
            self._emit(live, record)
            self.runtime.set_current_turn_context(
                live.id,
                sub_id,
                live.thread_id,
                agent_id=session_id,
                role="subagent",
            )
            memory = getattr(self.runtime, "memory", None)
            prompt = wrap_turn_prompt(
                record.task,
                (
                    memory.context_for_turn(live.id, record.task)
                    if memory is not None
                    else format_memory_context(self.store.memory_for_agent(live.id))
                ),
                role="subagent",
                clarifications=record.clarifications,
                steer=mode == "steer",
            )
            draft = ""
            result = ""
            status = "completed"
            error: str | None = None
            async for item in self.runtime.stream(
                prompt,
                session_id=session_id,
                bot_id=live.id,
                role="subagent",
            ):
                if isinstance(item, RunRecord):
                    result = item.result or draft or ""
                    if item.status not in {"finished", "completed"} and not result:
                        result = item.error or f"subagent failed: {item.id}"
                    if item.status in {"cancelled", "canceled"}:
                        status = "cancelled"
                    elif item.status not in {"finished", "completed"}:
                        status = "failed"
                    error = item.error if status != "completed" else None
                    continue
                if not isinstance(item, ProductStreamEvent):
                    continue
                if item.type == "thread.message.updated":
                    draft = accumulate(draft, item.payload)
                    if draft:
                        record = self.store.update_subagent(sub_id, progress=draft) or record
                        self._emit(live, record)
            if not result:
                result = draft or ""
            final = self.store.update_subagent(sub_id, status=status, result=result, error=error)
            if final:
                self._emit(live, final)
        except asyncio.CancelledError:
            current = self.tasks.get(sub_id)
            if current is not None and current is not asyncio.current_task():
                return
            record = self.store.get_subagent(sub_id)
            if record is None or record.status not in {"queued", "running"}:
                return
            if record.status == "queued":
                return
            updated = self.store.update_subagent(sub_id, status="cancelled", error="stopped")
            if updated:
                self._emit(live, updated)
        except Exception as exc:
            log.exception("subagent %s failed", sub_id)
            updated = self.store.update_subagent(sub_id, status="failed", error=str(exc))
            if updated:
                self._emit(live, updated)
        finally:
            self.runtime.clear_active_turn(run_id=sub_id)

    def payload(self, record: Subagent) -> dict[str, Any]:
        return {
            "agent_id": record.id,
            "name": record.name,
            "task": record.task,
            "status": record.status,
            "progress": record.progress,
            "thinking": record.thinking,
            "result": record.result,
            "index": record.index,
            "error": record.error,
            "clarifications": record.clarifications,
        }

    def _emit(self, bot: Bot, record: Subagent) -> None:
        if self.events is None:
            return
        event = ProductEvent(
            id=new_id("evt"),
            workspace_id=bot.workspace_id,
            thread_id=bot.thread_id,
            bot_id=bot.id,
            seq=self.events.next_seq(bot.id),
            type=ProductEventType.THREAD_SUBAGENT,
            created_at=isoformat_utc(),
            payload=self.payload(record),
            run_id=record.parent_run_id,
        )
        self.events.publish(event)
