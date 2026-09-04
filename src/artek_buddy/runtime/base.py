from __future__ import annotations

import contextvars
import json
import logging
import threading
from pathlib import Path
from typing import Any

from artek_buddy.config import Settings
from artek_buddy.runtime.types import AgentRuntimeError, RunRecord, ToolTurnBox, TurnContext

log = logging.getLogger("artek_buddy")

_current_turn_context: contextvars.ContextVar[tuple[str | None, str | None, str | None]] = (
    contextvars.ContextVar("current_turn_context", default=(None, None, None))
)
_current_turn_role: contextvars.ContextVar[str] = contextvars.ContextVar(
    "current_turn_role", default="lead"
)


class RuntimeBase:
    def __init__(
        self,
        settings: Settings,
        store: Any | None = None,
        computers: Any | None = None,
    ) -> None:
        self.settings = settings
        self.store = store
        self.computers = computers
        self.on_takeover_requested: Any | None = None
        self.on_bot_ask: Any | None = None
        self.default_agent_id: str | None = None
        self.last_prompt: str | None = None
        self.memory: Any | None = None
        self.consent: Any | None = None
        self.subagents: Any | None = None
        self.events: Any | None = None
        self.loop: Any | None = None
        self.owner_file_reader: Any | None = None
        self.owner_file_writer: Any | None = None
        self.owner_dir_lister: Any | None = None
        self.owner_command_runner: Any | None = None
        self.book_fixture_url: str = ""
        self._agents: dict[str, Any] = {}
        self._state_path = Path(settings.agent_data_dir) / "session.json"
        self._turn_lock = threading.Lock()
        self._active_turns: dict[str, tuple[str | None, str | None, str | None]] = {}
        self._turn_roles: dict[str, str] = {}
        self._frozen_by_run: dict[str, TurnContext] = {}
        self._frozen_by_agent: dict[str, TurnContext] = {}
        self._tool_boxes: dict[str, ToolTurnBox] = {}
        self._owner_intent: dict[str, str] = {}
        self._bot_by_agent: dict[str, str] = {}
        self._messages_sent_in_turn: set[str] = set()
        self._terminal_messages_sent_in_turn: set[str] = set()
        self._fresh_sessions: set[str] = set()
        self._cancelled_runs: set[str] = set()

    @staticmethod
    def normalize_turn_device(device_id: str | None) -> str | None:
        if not device_id or device_id == "host":
            return None
        return device_id

    def set_turn_device(self, device_id: str | None) -> None:
        """Kept so callers cannot reintroduce a process-global device. Bind via freeze."""
        del device_id

    def resolve_turn_device(self, bound_bot_id: str | None = None) -> str | None:
        found = self.resolve_turn(bound_bot_id)
        if found is None:
            return None
        return found.device_id

    def bind_agent_bot(self, agent_id: str | None, bot_id: str | None) -> None:
        if not agent_id or not bot_id:
            return
        with self._turn_lock:
            self._bot_by_agent[agent_id] = bot_id

    def session_foreign_to_bot(self, agent_id: str | None, bot_id: str | None) -> bool:
        if not agent_id or not bot_id:
            return False
        with self._turn_lock:
            bound = self._bot_by_agent.get(agent_id)
        if bound and bound != bot_id:
            return True
        store = self.store
        getter = getattr(store, "get_bot_by_agent", None) if store is not None else None
        if getter is None:
            return False
        try:
            owner = getter(agent_id)
        except Exception:
            return False
        return owner is not None and getattr(owner, "id", None) != bot_id

    def mark_session_fresh(self, agent_id: str | None) -> None:
        if not agent_id:
            return
        with self._turn_lock:
            self._fresh_sessions.add(agent_id)

    def consume_session_fresh(self, agent_id: str | None) -> bool:
        if not agent_id:
            return False
        with self._turn_lock:
            if agent_id not in self._fresh_sessions:
                return False
            self._fresh_sessions.remove(agent_id)
        return True

    def mark_runs_cancelled(self, run_ids: list[str]) -> None:
        ids = [item for item in run_ids if item]
        if not ids:
            return
        with self._turn_lock:
            self._cancelled_runs.update(ids)

    def is_run_cancelled(self, run_id: str | None) -> bool:
        if not run_id:
            return False
        with self._turn_lock:
            if run_id in self._cancelled_runs:
                return True
        store = self.store
        getter = getattr(store, "get_run", None)
        if not callable(getter):
            return False
        try:
            row = getter(run_id)
        except Exception:
            log.exception("failed to read run cancel state")
            return False
        if row is None:
            return False
        status = getattr(row.status, "value", None) or str(row.status)
        return status not in {
            "queued",
            "leased",
            "running",
            "waiting_input",
            "waiting_takeover",
        }

    def build_session_resume(self, bot_id: str | None) -> str | None:
        if not bot_id or self.store is None:
            return None
        try:
            from artek_buddy.memory import format_memory_context, format_session_resume

            bot = self.store.get_bot(bot_id)
            if bot is None:
                return None
            page = self.store.page_messages(bot.thread_id, limit=40)
            if self.memory is not None:
                memory_context = self.memory.context_for_turn(
                    bot.id, "current work repository path branch"
                )
            else:
                memory_context = format_memory_context(self.store.memory_for_agent(bot.id))
            return format_session_resume(
                home_cwd=self.home_cwd(bot.id),
                bot=bot,
                memory_context=memory_context,
                messages=page.messages,
            )
        except Exception:
            log.exception("failed to build fresh-session resume")
            return None

    def set_current_turn_context(
        self,
        bot_id: str | None,
        run_id: str | None,
        thread_id: str | None,
        agent_id: str | None = None,
        role: str = "lead",
        device_id: str | None = None,
    ) -> Any:
        turn_role = role if role in {"lead", "subagent"} else "lead"
        token = _current_turn_context.set((bot_id, run_id, thread_id))
        _current_turn_role.set(turn_role)
        turn_device = self.normalize_turn_device(device_id)
        if turn_device is None and turn_role == "subagent" and run_id:
            turn_device = self._inherit_parent_device(run_id)
        if bot_id and run_id:
            self.freeze_turn(
                TurnContext(
                    bot_id=bot_id,
                    run_id=run_id,
                    thread_id=thread_id or "",
                    role=turn_role,
                    agent_id=agent_id,
                    device_id=turn_device,
                )
            )
        elif agent_id and bot_id:
            self.bind_agent_bot(agent_id, bot_id)
        return token

    def _inherit_parent_device(self, run_id: str) -> str | None:
        store = self.store
        getter = getattr(store, "get_subagent", None) if store is not None else None
        if not callable(getter):
            return None
        try:
            found = getter(run_id)
        except Exception:
            return None
        parent_id = getattr(found, "parent_run_id", None) if found is not None else None
        if not parent_id:
            return None
        with self._turn_lock:
            parent = self._frozen_by_run.get(parent_id)
        if parent is None:
            return None
        return parent.device_id

    def device_for_run(self, run_id: str | None) -> str | None:
        if not run_id:
            return None
        with self._turn_lock:
            frozen = self._frozen_by_run.get(run_id)
        if frozen is None:
            return None
        return frozen.device_id

    def freeze_turn(self, ctx: TurnContext) -> None:
        with self._turn_lock:
            self._frozen_by_run[ctx.run_id] = ctx
            self._active_turns[ctx.run_id] = (ctx.bot_id, ctx.run_id, ctx.thread_id)
            self._turn_roles[ctx.run_id] = ctx.role
            if ctx.agent_id:
                self._frozen_by_agent[ctx.agent_id] = ctx
                self._bot_by_agent[ctx.agent_id] = ctx.bot_id
                box = self._tool_boxes.get(ctx.agent_id)
                if box is not None:
                    box.agent_id = ctx.agent_id
                    box.turn = ctx

    def register_tool_box(self, agent_id: str, box: ToolTurnBox) -> None:
        box.agent_id = agent_id
        with self._turn_lock:
            self._tool_boxes[agent_id] = box
            frozen = self._frozen_by_agent.get(agent_id)
        if frozen is not None:
            box.turn = frozen

    def set_owner_intent(self, run_id: str | None, intent: str) -> None:
        if not run_id:
            return
        value = intent if intent in {"status", "correction", "other"} else "other"
        with self._turn_lock:
            self._owner_intent[run_id] = value

    def owner_intent_for(self, run_id: str | None) -> str:
        if not run_id:
            return "other"
        with self._turn_lock:
            return self._owner_intent.get(run_id, "other")

    def apply_callback_context(self, ctx: TurnContext) -> tuple[Any, Any]:
        token = _current_turn_context.set((ctx.bot_id, ctx.run_id, ctx.thread_id))
        role_token = _current_turn_role.set(ctx.role)
        return token, role_token

    def reset_callback_context(self, tokens: tuple[Any, Any]) -> None:
        _current_turn_context.reset(tokens[0])
        _current_turn_role.reset(tokens[1])

    def resolve_turn(
        self,
        bound_bot_id: str | None = None,
        agent_id: str | None = None,
    ) -> TurnContext | None:
        ctx = _current_turn_context.get()
        if ctx[1]:
            with self._turn_lock:
                frozen = self._frozen_by_run.get(ctx[1])
            if frozen is not None and (not bound_bot_id or frozen.bot_id == bound_bot_id):
                return frozen
        with self._turn_lock:
            if agent_id:
                frozen = self._frozen_by_agent.get(agent_id)
                if frozen is not None and (not bound_bot_id or frozen.bot_id == bound_bot_id):
                    return frozen
            active = list(self._frozen_by_run.values())
        if bound_bot_id:
            matching = [item for item in active if item.bot_id == bound_bot_id]
            if len(matching) == 1:
                return matching[0]
            return None
        if len(active) == 1:
            return active[0]
        return None

    def has_sent_message_in_turn(self, run_id: str | None) -> bool:
        if not run_id:
            return False
        with self._turn_lock:
            return run_id in self._messages_sent_in_turn

    def has_sent_terminal_message_in_turn(self, run_id: str | None) -> bool:
        if not run_id:
            return False
        with self._turn_lock:
            return run_id in self._terminal_messages_sent_in_turn

    def mark_message_sent(self, run_id: str | None, *, terminal: bool = False) -> None:
        if not run_id:
            return
        with self._turn_lock:
            self._messages_sent_in_turn.add(run_id)
            if terminal:
                self._terminal_messages_sent_in_turn.add(run_id)

    def clear_active_turn(self, bot_id: str | None = None, run_id: str | None = None) -> None:
        with self._turn_lock:
            if run_id:
                self._active_turns.pop(run_id, None)
                self._turn_roles.pop(run_id, None)
                self._frozen_by_run.pop(run_id, None)
                self._messages_sent_in_turn.discard(run_id)
                self._terminal_messages_sent_in_turn.discard(run_id)
                self._owner_intent.pop(run_id, None)
                for agent_id, frozen in list(self._frozen_by_agent.items()):
                    if frozen.run_id == run_id:
                        self._frozen_by_agent.pop(agent_id, None)
                        box = self._tool_boxes.get(agent_id)
                        if box is not None:
                            box.turn = None
                return
            if not bot_id:
                return
            for key, value in list(self._active_turns.items()):
                if key == bot_id or value[0] == bot_id:
                    self._active_turns.pop(key, None)
                    self._turn_roles.pop(key, None)
                    self._frozen_by_run.pop(key, None)
                    self._messages_sent_in_turn.discard(key)
                    self._terminal_messages_sent_in_turn.discard(key)
                    self._owner_intent.pop(key, None)
            for agent_id, frozen in list(self._frozen_by_agent.items()):
                if frozen.bot_id == bot_id:
                    self._frozen_by_agent.pop(agent_id, None)
                    box = self._tool_boxes.get(agent_id)
                    if box is not None:
                        box.turn = None

    def get_current_turn_context(self) -> tuple[str | None, str | None, str | None]:
        return self.resolve_turn_context()

    def resolve_turn_context(
        self,
        bound_bot_id: str | None = None,
    ) -> tuple[str | None, str | None, str | None]:
        found = self.resolve_turn(bound_bot_id)
        if found is None:
            return (None, None, None)
        return (found.bot_id, found.run_id, found.thread_id)

    def resolve_turn_role(self, bound_bot_id: str | None = None) -> str:
        found = self.resolve_turn(bound_bot_id)
        if found is not None:
            return found.role
        return "lead"

    def home_cwd(self, bot_id: str | None = None) -> str:
        if bot_id and self.store is not None:
            try:
                bot = self.store.get_bot(bot_id)
                if bot is not None:
                    record = self.store.get_computer_for_bot(bot)
                    path = Path(self.settings.agent_data_dir) / "homes" / record.home_key
                    path.mkdir(parents=True, exist_ok=True)
                    agents = path / "AGENTS.md"
                    if not agents.exists():
                        template = Path(self.settings.agent_cwd) / "AGENTS.md"
                        if template.is_file():
                            agents.write_text(
                                template.read_text(encoding="utf-8"), encoding="utf-8"
                            )
                    return str(path)
            except Exception:
                log.exception("failed to resolve computer home")
        return self.settings.agent_cwd

    def _ensure_dirs(self) -> None:
        Path(self.settings.agent_data_dir).mkdir(parents=True, exist_ok=True)
        Path(self.settings.agent_cwd).mkdir(parents=True, exist_ok=True)

    def _load_state(self) -> str | None:
        if not self._state_path.exists():
            return None
        try:
            return json.loads(self._state_path.read_text()).get("agent_id")
        except Exception:
            return None

    def _save_state(self, agent_id: str) -> None:
        self._state_path.parent.mkdir(parents=True, exist_ok=True)
        self._state_path.write_text(json.dumps({"agent_id": agent_id}))

    async def send(self, prompt: str, session_id: str | None = None) -> RunRecord:
        record: RunRecord | None = None
        async for item in self.stream(prompt, session_id=session_id):
            if isinstance(item, RunRecord):
                record = item
        if record is None:
            raise AgentRuntimeError("stream ended without a run record")
        return record
