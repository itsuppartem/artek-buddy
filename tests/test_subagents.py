from __future__ import annotations

import unittest
from types import SimpleNamespace
from typing import AsyncIterator

from artek_buddy.contracts.domain import Subagent
from artek_buddy.runtime.types import RunRecord
from artek_buddy.subagents import SubagentService


class _Runtime:
    async def create_session(self, **_kwargs: object) -> str:
        return "agent-1"

    def bind_agent_bot(self, *_args: object) -> None:
        return None

    def set_current_turn_context(self, *_args: object, **_kwargs: object) -> None:
        return None

    def clear_active_turn(self, *_args: object, **_kwargs: object) -> None:
        return None

    async def stream(self, *_args: object, **_kwargs: object) -> AsyncIterator[RunRecord]:
        yield RunRecord(
            id="run-1",
            agent_id="agent-1",
            status="failed",
            result=None,
            error="model timeout",
        )


class _Store:
    def __init__(self, record: Subagent) -> None:
        self.record = record

    def get_subagent(self, sub_id: str) -> Subagent | None:
        return self.record if sub_id == self.record.id else None

    def get_bot(self, _bot_id: str) -> None:
        return None

    def memory_for_agent(self, _bot_id: str) -> list[object]:
        return []

    def update_subagent(self, sub_id: str, **changes: object) -> Subagent | None:
        if sub_id != self.record.id:
            return None
        self.record = self.record.model_copy(update=changes)
        return self.record


class SubagentFailureTest(unittest.IsolatedAsyncioTestCase):
    async def test_failed_runtime_record_marks_the_worker_failed(self) -> None:
        record = Subagent(
            id="sub-1",
            bot_id="bot-1",
            thread_id="thread-1",
            index=1,
            name="worker",
            task="inspect",
            status="queued",
            created_at="2026-08-18T00:00:00Z",
            updated_at="2026-08-18T00:00:00Z",
        )
        store = _Store(record)
        service = SubagentService(store, _Runtime())  # type: ignore[arg-type]
        bot = SimpleNamespace(id="bot-1", thread_id="thread-1")

        await service._run(bot, record.id)

        self.assertEqual(store.record.status, "failed")
        self.assertEqual(store.record.error, "model timeout")
        self.assertEqual(store.record.result, "model timeout")
