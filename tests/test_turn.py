from __future__ import annotations

import asyncio
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from artek_buddy.bus import EventHub
from artek_buddy.config import Settings
from artek_buddy.contracts.domain import Bot, Run
from artek_buddy.contracts.events import MessageRole, ProductEventType, ThreadMessage
from artek_buddy.contracts.ids import RunStatus
from artek_buddy.main import _run_turn, app
from artek_buddy.runtime import (
    ScriptedRuntime,
    ScriptedStep,
    scripted_finish,
    scripted_text,
    scripted_tool,
)


def _settings() -> Settings:
    root = Path(tempfile.mkdtemp(prefix="artek-buddy-turn-"))
    return Settings(
        agent_http_token="test-token",
        agent_runtime="scripted",
        agent_cwd=str(root / "cwd"),
        agent_data_dir=str(root / "data"),
    )


def _bot() -> Bot:
    return Bot(
        id="bot_1",
        workspace_id="ws_1",
        name="Test",
        title="",
        description="",
        instructions="",
        color="#888888",
        notify_on_finish=True,
        pinned=False,
        archived_at=None,
        unread=False,
        parent_bot_id=None,
        thread_id="th_1",
        preview="",
        status="idle",
        computer_mode="team",
        cursor_agent_id="sa-1",
        updated_at="2026-08-18T00:00:00Z",
        created_at="2026-08-18T00:00:00Z",
    )


def _run(bot: Bot, run_id: str = "run_1") -> Run:
    return Run(
        id=run_id,
        bot_id=bot.id,
        thread_id=bot.thread_id,
        task_id=f"tsk_{run_id}",
        status=RunStatus.running,
        trigger="user",
        model_provider="scripted",
        model_id="grok-4.6",
        error=None,
        started_at="2026-08-18T00:00:00Z",
        completed_at=None,
    )


class _Store:
    def __init__(self, bot: Bot) -> None:
        self.bot = bot
        self.finished: list[dict[str, object]] = []
        self.saved: list[dict[str, object]] = []
        self.inbox: list[dict[str, str | None]] = []

    def memory_for_agent(self, bot_id: str) -> list[object]:
        return []

    def list_subagents(self, bot_id: str) -> list[object]:
        return []

    def attach_agent(self, bot_id: str, agent_id: str) -> Bot:
        self.bot = self.bot.model_copy(update={"cursor_agent_id": agent_id})
        return self.bot

    def get_bot(self, bot_id: str) -> Bot | None:
        return self.bot if bot_id == self.bot.id else None

    def finish_turn(
        self,
        bot: Bot,
        run: Run,
        text: str,
        status: str,
        error: str | None = None,
    ) -> tuple[ThreadMessage | None, Run]:
        finished = run.model_copy(
            update={
                "status": RunStatus(status),
                "error": error,
                "completed_at": "2026-08-18T00:00:01Z",
            }
        )
        self.finished.append({"text": text, "status": status, "error": error})
        if not text:
            return None, finished
        msg = ThreadMessage(
            id="msg_bot",
            thread_id=bot.thread_id,
            seq=2,
            role=MessageRole.bot,
            blocks=[{"kind": "text", "text": text}],
            created_at="2026-08-18T00:00:01Z",
            run_id=run.id,
        )
        return msg, finished

    def drain_inbox(self, bot_id: str) -> list[dict[str, str | None]]:
        items = list(self.inbox)
        self.inbox = []
        return items

    def has_active_run(self, bot_id: str) -> bool:
        return False

    def begin_run(self, bot: Bot, trigger: str = "follow_up", **kwargs: object) -> Run:
        return _run(bot, run_id="run_inbox")

    def save_memory(self, **kwargs: object) -> SimpleNamespace:
        self.saved.append(kwargs)
        return SimpleNamespace(
            id="mem_1",
            revision=1,
            path=kwargs.get("path", "MEMORY.md"),
            scope=kwargs.get("scope", "bot"),
        )

    def waiting_takeover_run(self, bot_id: str) -> None:
        return None


class TurnPipelineTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        app.state.active_turns = {}

    async def test_run_turn_completes_from_scripted_reply(self) -> None:
        bot = _bot()
        store = _Store(bot)
        runtime = ScriptedRuntime(_settings(), store=store)
        await runtime.start()
        runtime.queue_turn(scripted_text("Belgrade is 22 C"), scripted_finish("Belgrade is 22 C"))
        events = EventHub()
        await _run_turn(store, runtime, events, bot, "weather?", _run(bot))
        self.assertEqual(store.finished[-1]["status"], "completed")
        self.assertEqual(store.finished[-1]["text"], "Belgrade is 22 C")
        types = [item.type for item in events.replay(bot.id)]
        self.assertNotIn(ProductEventType.THREAD_MESSAGE_UPDATED, types)
        self.assertNotIn(ProductEventType.THREAD_PROGRESS, types)
        self.assertIn(ProductEventType.THREAD_MESSAGE_CREATED, types)
        self.assertIn(ProductEventType.RUN_COMPLETED, types)

    async def test_run_turn_remember_and_runtime_error(self) -> None:
        bot = _bot()
        store = _Store(bot)
        runtime = ScriptedRuntime(_settings(), store=store)
        await runtime.start()
        runtime.set_current_turn_context(bot.id, "run_1", bot.thread_id)
        runtime.queue_turn(
            scripted_tool("remember", content="Likes tea", path="NOTES.md"),
            scripted_text("Saved."),
            scripted_finish("Saved."),
        )
        events = EventHub()
        await _run_turn(store, runtime, events, bot, "remember this", _run(bot))
        self.assertEqual(store.saved[0]["content"], "Likes tea")
        self.assertEqual(store.finished[-1]["status"], "completed")
        types = [item.type for item in events.replay(bot.id)]
        self.assertIn(ProductEventType.THREAD_META, types)

        runtime.queue_turn(ScriptedStep(raise_error="no cloud"))
        events = EventHub()
        await _run_turn(store, runtime, events, bot, "again", _run(bot, run_id="run_2"))
        self.assertEqual(store.finished[-1]["status"], "failed")
        self.assertEqual(store.finished[-1]["error"], "no cloud")
        self.assertIn(ProductEventType.RUN_FAILED, [item.type for item in events.replay(bot.id)])

    async def test_inbox_follow_up_uses_the_same_scripted_runtime(self) -> None:
        bot = _bot()
        store = _Store(bot)
        store.inbox = [{"message_id": "m2", "text": "and this", "reply_to_id": None}]
        runtime = ScriptedRuntime(_settings(), store=store)
        await runtime.start()
        runtime.queue_turn(scripted_text("first"), scripted_finish("first"))
        runtime.queue_turn(scripted_text("second"), scripted_finish("second"))
        events = EventHub()
        await _run_turn(store, runtime, events, bot, "first task", _run(bot))
        pending = [task for task in asyncio.all_tasks() if task.get_name() == "turn-run_inbox"]
        if pending:
            await pending[0]
        self.assertGreaterEqual(len(store.finished), 2)
        self.assertEqual(store.finished[0]["text"], "first")
        self.assertEqual(store.finished[-1]["text"], "second")
