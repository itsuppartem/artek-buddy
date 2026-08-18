from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from artek_buddy.config import Settings
from artek_buddy.runtime import (
    AgentRuntimeError,
    CursorRuntime,
    ProductStreamEvent,
    ProductTools,
    RunRecord,
    ScriptedRuntime,
    open_runtime,
    scripted_finish,
    scripted_text,
    scripted_tool,
)


def _settings(*, runtime: str = "scripted", key: str = "") -> Settings:
    root = Path(tempfile.mkdtemp(prefix="artek-buddy-scripted-"))
    return Settings(
        cursor_api_key=key,
        agent_http_token="test-token",
        agent_runtime=runtime,
        agent_cwd=str(root / "cwd"),
        agent_data_dir=str(root / "data"),
    )


class ScriptedRuntimeTest(unittest.IsolatedAsyncioTestCase):
    async def test_starts_without_cursor_key(self) -> None:
        runtime = ScriptedRuntime(_settings())
        await runtime.start()
        self.assertTrue(runtime.default_agent_id)
        self.assertTrue((Path(runtime.settings.agent_data_dir) / "session.json").exists())
        models = await runtime.list_models()
        self.assertEqual(models[0]["id"], "grok-4.6")

    async def test_default_stream_is_product_shaped(self) -> None:
        runtime = ScriptedRuntime(_settings())
        await runtime.start()
        items: list[object] = []
        async for item in runtime.stream("hello"):
            items.append(item)
        self.assertIsInstance(items[0], ProductStreamEvent)
        self.assertEqual(items[0].type, "thread.message.updated")
        self.assertIsInstance(items[-1], RunRecord)
        self.assertEqual(items[-1].status, "completed")

    async def test_queued_turn_calls_remember(self) -> None:
        class _Store:
            def __init__(self) -> None:
                self.saved: list[dict[str, object]] = []

            def save_memory(self, **kwargs: object) -> SimpleNamespace:
                self.saved.append(kwargs)
                return SimpleNamespace(
                    id="mem_1",
                    revision=1,
                    path=kwargs.get("path", "MEMORY.md"),
                    scope=kwargs.get("scope", "bot"),
                )

        store = _Store()
        runtime = ScriptedRuntime(_settings(), store=store)
        await runtime.start()
        runtime.set_current_turn_context("bot_1", "run_1", "th_1")
        runtime.queue_turn(
            scripted_tool("remember", content="Likes tea", path="NOTES.md"),
            scripted_text("Noted."),
            scripted_finish("Noted."),
        )
        record = await runtime.send("remember this")
        self.assertEqual(record.status, "completed")
        self.assertEqual(record.result, "Noted.")
        self.assertEqual(store.saved[0]["content"], "Likes tea")
        self.assertEqual(store.saved[0]["path"], "NOTES.md")
        self.assertEqual(runtime.last_tool_results[0][0], "remember")

    async def test_raise_error_step(self) -> None:
        from artek_buddy.runtime.scripted import ScriptedStep

        runtime = ScriptedRuntime(_settings())
        await runtime.start()
        runtime.queue_turn(ScriptedStep(raise_error="boom"))
        with self.assertRaises(AgentRuntimeError) as ctx:
            await runtime.send("fail")
        self.assertEqual(ctx.exception.message, "boom")

    async def test_factory_scripted_and_rejects_unknown(self) -> None:
        async with open_runtime(_settings()) as runtime:
            self.assertIsInstance(runtime, ScriptedRuntime)
            self.assertTrue(runtime.default_agent_id)
        with self.assertRaises(AgentRuntimeError):
            async with open_runtime(_settings(runtime="nope")):
                pass
        with self.assertRaises(AgentRuntimeError):
            async with open_runtime(_settings(runtime="cursor", key="")):
                pass


class ProductToolsRegistryTest(unittest.TestCase):
    def test_lead_has_workers_subagent_does_not(self) -> None:
        runtime = ScriptedRuntime(_settings())
        tools = ProductTools(runtime)
        lead = tools.names("lead")
        worker = tools.names("subagent")
        self.assertIn("remember", lead)
        self.assertIn("spawn_subagent", lead)
        self.assertIn("remember", worker)
        self.assertNotIn("spawn_subagent", worker)
        self.assertNotIn("request_takeover", worker)

    def test_cursor_runtime_is_not_the_host_protocol_class(self) -> None:
        self.assertTrue(issubclass(CursorRuntime, object))
        self.assertIsNot(CursorRuntime, ScriptedRuntime)
