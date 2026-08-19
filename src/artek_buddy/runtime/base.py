from __future__ import annotations

import contextvars
import json
import logging
import threading
from pathlib import Path
from typing import Any

from artek_buddy.config import Settings
from artek_buddy.runtime.types import AgentRuntimeError, RunRecord

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
        self.default_agent_id: str | None = None
        self.memory: Any | None = None
        self.consent: Any | None = None
        self.subagents: Any | None = None
        self.events: Any | None = None
        self.loop: Any | None = None
        self.owner_file_reader: Any | None = None
        self.owner_file_writer: Any | None = None
        self.owner_dir_lister: Any | None = None
        self.owner_command_runner: Any | None = None
        self._agents: dict[str, Any] = {}
        self._state_path = Path(settings.agent_data_dir) / "session.json"
        self._turn_lock = threading.Lock()
        self._active_turns: dict[str, tuple[str | None, str | None, str | None]] = {}
        self._last_turn: tuple[str | None, str | None, str | None] = (None, None, None)
        self._turn_roles: dict[str, str] = {}
        self._last_role: str = "lead"
        self._last_device: str | None = None
        self._bot_by_agent: dict[str, str] = {}
        self._messages_sent_in_turn: set[str] = set()

    def set_turn_device(self, device_id: str | None) -> None:
        self._last_device = device_id if device_id and device_id != "host" else None

    def resolve_turn_device(self) -> str | None:
        return self._last_device

    def bind_agent_bot(self, agent_id: str | None, bot_id: str | None) -> None:
        if not agent_id or not bot_id:
            return
        with self._turn_lock:
            self._bot_by_agent[agent_id] = bot_id

    def set_current_turn_context(
        self,
        bot_id: str | None,
        run_id: str | None,
        thread_id: str | None,
        agent_id: str | None = None,
        role: str = "lead",
    ) -> Any:
        turn_role = role if role in {"lead", "subagent"} else "lead"
        token = _current_turn_context.set((bot_id, run_id, thread_id))
        _current_turn_role.set(turn_role)
        with self._turn_lock:
            self._last_turn = (bot_id, run_id, thread_id)
            self._last_role = turn_role
            slot = run_id or bot_id
            if slot:
                self._active_turns[slot] = (bot_id, run_id, thread_id)
                self._turn_roles[slot] = turn_role
            if agent_id and bot_id:
                self._bot_by_agent[agent_id] = bot_id
        return token

    def has_sent_message_in_turn(self, run_id: str | None) -> bool:
        return bool(run_id and run_id in self._messages_sent_in_turn)

    def mark_message_sent(self, run_id: str | None) -> None:
        if run_id:
            self._messages_sent_in_turn.add(run_id)

    def clear_active_turn(self, bot_id: str | None = None, run_id: str | None = None) -> None:
        with self._turn_lock:
            if run_id:
                self._active_turns.pop(run_id, None)
                self._turn_roles.pop(run_id, None)
                self._messages_sent_in_turn.discard(run_id)
                return
            if not bot_id:
                return
            for key, value in list(self._active_turns.items()):
                if key == bot_id or value[0] == bot_id:
                    self._active_turns.pop(key, None)
                    self._turn_roles.pop(key, None)

    def get_current_turn_context(self) -> tuple[str | None, str | None, str | None]:
        return self.resolve_turn_context()

    def resolve_turn_context(
        self,
        bound_bot_id: str | None = None,
    ) -> tuple[str | None, str | None, str | None]:
        # Custom tools run on the SDK callback thread. ContextVar from the
        # asyncio turn task is empty there; keep a process-local copy.
        ctx = _current_turn_context.get()
        if ctx[0]:
            return ctx
        with self._turn_lock:
            active = dict(self._active_turns)
            last = self._last_turn
            bot_by_agent = dict(self._bot_by_agent)
        if bound_bot_id:
            matching = [item for item in active.values() if item[0] == bound_bot_id]
            if len(matching) == 1:
                return matching[0]
            if last[0] == bound_bot_id:
                return last
            if matching:
                return matching[-1]
            return (bound_bot_id, last[1], last[2])
        if len(active) == 1:
            return next(iter(active.values()))
        bots = {item[0] for item in active.values() if item[0]}
        if len(bots) == 1 and last[0] in bots:
            return last
        if last[0]:
            return last
        if self.store is not None:
            for agent_id in (self.default_agent_id, *self._agents, *bot_by_agent):
                if not agent_id:
                    continue
                try:
                    bot = self.store.get_bot_by_agent(agent_id)
                except Exception:
                    bot = None
                if bot is not None:
                    return (bot.id, None, bot.thread_id)
        return (None, None, None)

    def resolve_turn_role(self, bound_bot_id: str | None = None) -> str:
        ctx = _current_turn_context.get()
        if ctx[0]:
            role = _current_turn_role.get()
            if role in {"lead", "subagent"}:
                return role
        bot_id, run_id, _thread_id = self.resolve_turn_context(bound_bot_id)
        with self._turn_lock:
            roles = dict(self._turn_roles)
            last = self._last_role
        if run_id and run_id in roles:
            return roles[run_id]
        if bot_id and bot_id in roles:
            return roles[bot_id]
        return last if last in {"lead", "subagent"} else "lead"

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
                            agents.write_text(template.read_text(encoding="utf-8"), encoding="utf-8")
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
