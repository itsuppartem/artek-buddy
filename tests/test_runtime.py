from __future__ import annotations

import json
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace

from cursor_sdk import AgentOptions, LocalAgentOptions
from cursor_sdk.types import options_to_json

from artek_buddy.config import Settings
from artek_buddy.runtime import CursorRuntime


def _settings(data_dir: str | None = None) -> Settings:
    root = Path(data_dir or tempfile.mkdtemp(prefix="artek-buddy-test-"))
    return Settings(
        cursor_api_key="crsr_test_key",
        agent_http_token="test-token",
        agent_cwd=str(root / "cwd"),
        agent_data_dir=str(root / "data"),
    )


class _Agents:
    def __init__(self, *, resume_error: Exception | None = None) -> None:
        self.resume_error = resume_error
        self.resume_calls: list[tuple[str, object]] = []
        self.create_calls = 0

    async def resume(self, agent_id: str, options: object) -> SimpleNamespace:
        self.resume_calls.append((agent_id, options))
        if self.resume_error is not None:
            raise self.resume_error
        return SimpleNamespace(agent_id=agent_id)

    async def create(self, **kwargs: object) -> SimpleNamespace:
        self.create_calls += 1
        return SimpleNamespace(agent_id="bc-new")


class _Client:
    def __init__(self, agents: _Agents) -> None:
        self.agents = agents


class RuntimeOptionsTest(unittest.TestCase):
    def test_resume_options_are_json_serializable(self) -> None:
        runtime = CursorRuntime(_Client(_Agents()), _settings())
        options = runtime._agent_options()
        self.assertIsInstance(options, AgentOptions)
        self.assertIsInstance(options.local, LocalAgentOptions)
        wire = options_to_json(options)
        encoded = json.dumps(wire)
        self.assertIn('"local"', encoded)
        self.assertNotIn("LocalAgentOptions", encoded)

    def test_raw_local_object_in_a_dict_is_not_serializable(self) -> None:
        runtime = CursorRuntime(_Client(_Agents()), _settings())
        broken = {"local": runtime._local()}
        with self.assertRaises(TypeError):
            json.dumps(broken)

    def test_custom_tools_contains_remember(self) -> None:
        class _MockStore:
            def __init__(self) -> None:
                self.saved: list[dict[str, object]] = []

            def save_memory(self, **kwargs: object) -> SimpleNamespace:
                self.saved.append(kwargs)
                return SimpleNamespace(id="mem_123", revision=1, path=kwargs.get("path", "MEMORY.md"), scope=kwargs.get("scope", "bot"))

        store = _MockStore()
        runtime = CursorRuntime(_Client(_Agents()), _settings(), store=store)
        tools = runtime._custom_tools()
        self.assertIn("remember", tools)
        self.assertIn("send_message", tools)
        self.assertIn("ask_user", tools)
        self.assertIn("open_path", tools)
        self.assertIn("launch_app", tools)
        self.assertIn("close_app", tools)
        self.assertIn("computer_observe", tools)
        self.assertIn("computer_act", tools)
        self.assertIn("request_takeover", tools)
        self.assertIn("spawn_subagent", tools)
        self.assertIn("inspect_subagent", tools)
        self.assertIn("steer_subagent", tools)
        self.assertIn("send_message", runtime._custom_tools(role="subagent"))
        self.assertIn("ask_user", runtime._custom_tools(role="subagent"))
        self.assertIn("open_path", runtime._custom_tools(role="subagent"))
        self.assertIn("launch_app", runtime._custom_tools(role="subagent"))
        self.assertIn("close_app", runtime._custom_tools(role="subagent"))
        self.assertNotIn("spawn_subagent", runtime._custom_tools(role="subagent"))
        self.assertNotIn("steer_subagent", runtime._custom_tools(role="subagent"))
        self.assertNotIn("request_takeover", runtime._custom_tools(role="subagent"))
        rem_tool = tools["remember"]
        self.assertEqual(rem_tool.input_schema["required"], ["content"])

        # Test execute without content
        res = rem_tool.execute({}, SimpleNamespace(tool_call_id="c1"))
        self.assertFalse(res["ok"])

        # Test execute with turn context
        runtime.set_current_turn_context("bot_42", "run_99", "th_1")
        res = rem_tool.execute({"content": "Likes dark mode", "path": "PREFERENCES.md"}, SimpleNamespace(tool_call_id="c2"))
        self.assertTrue(res["ok"])
        self.assertEqual(res["document_id"], "mem_123")
        self.assertEqual(len(store.saved), 1)
        self.assertEqual(store.saved[0]["bot_id"], "bot_42")
        self.assertEqual(store.saved[0]["path"], "PREFERENCES.md")
        self.assertEqual(store.saved[0]["content"], "Likes dark mode")

    def test_computer_observe_reaches_the_box_from_the_callback_thread(self) -> None:
        bot = SimpleNamespace(id="bot_42", thread_id="th_1", name="test")

        class _Store:
            def get_bot(self, bot_id: str) -> SimpleNamespace | None:
                return bot if bot_id == "bot_42" else None

            def get_bot_by_agent(self, _agent_id: str) -> SimpleNamespace | None:
                return None

        class _Computers:
            def __init__(self) -> None:
                self.seen: list[str] = []

            def observe(self, found: SimpleNamespace) -> dict[str, object]:
                self.seen.append(found.id)
                return {"ok": True, "window": "Chromium"}

        computers = _Computers()
        runtime = CursorRuntime(
            _Client(_Agents()),
            _settings(),
            store=_Store(),
            computers=computers,
        )
        runtime.set_current_turn_context("bot_42", "run_99", "th_1")
        tool = runtime._custom_tools()["computer_observe"]
        result: dict[str, object] = {}

        def other_thread() -> None:
            result["out"] = tool.execute({}, SimpleNamespace(tool_call_id="c3"))

        worker = threading.Thread(target=other_thread)
        worker.start()
        worker.join(timeout=2)
        self.assertFalse(worker.is_alive())
        self.assertEqual(result["out"], {"ok": True, "window": "Chromium"})
        self.assertEqual(computers.seen, ["bot_42"])

    def test_computer_observe_without_a_turn_is_unavailable(self) -> None:
        runtime = CursorRuntime(_Client(_Agents()), _settings())
        tool = runtime._custom_tools()["computer_observe"]
        res = tool.execute({}, SimpleNamespace(tool_call_id="c4"))
        self.assertEqual(res, {"ok": False, "error": "computer is not available"})

    def test_computer_act_from_callback_thread(self) -> None:
        bot = SimpleNamespace(id="bot_42", thread_id="th_1", name="test")

        class _Store:
            def get_bot(self, bot_id: str) -> SimpleNamespace | None:
                return bot if bot_id == "bot_42" else None

            def get_bot_by_agent(self, _agent_id: str) -> SimpleNamespace | None:
                return None

        class _Computers:
            def act(self, found: SimpleNamespace, actions: list[object]) -> dict[str, object]:
                return {"ok": True, "bot": found.id, "n": len(actions)}

        runtime = CursorRuntime(
            _Client(_Agents()),
            _settings(),
            store=_Store(),
            computers=_Computers(),
        )
        runtime.set_current_turn_context("bot_42", "run_99", "th_1")
        tool = runtime._custom_tools()["computer_act"]
        result: dict[str, object] = {}

        def other_thread() -> None:
            result["out"] = tool.execute(
                {"actions": [{"type": "click", "x": 10, "y": 20}]},
                SimpleNamespace(tool_call_id="c5"),
            )

        worker = threading.Thread(target=other_thread)
        worker.start()
        worker.join(timeout=2)
        self.assertEqual(result["out"], {"ok": True, "bot": "bot_42", "n": 1})

    def test_open_path_and_launch_app_from_callback_thread(self) -> None:
        bot = SimpleNamespace(id="bot_42", thread_id="th_1", name="test")

        class _Store:
            def get_bot(self, bot_id: str) -> SimpleNamespace | None:
                return bot if bot_id == "bot_42" else None

            def get_bot_by_agent(self, _agent_id: str) -> SimpleNamespace | None:
                return None

        class _Computers:
            def open_path(self, found: SimpleNamespace, path: str) -> dict[str, object]:
                return {"ok": True, "bot": found.id, "path": path}

            def launch_app(self, found: SimpleNamespace, name: str, uri: str | None = None) -> dict[str, object]:
                return {"ok": True, "bot": found.id, "app": name, "uri": uri}

            def close_app(self, found: SimpleNamespace, name: str) -> dict[str, object]:
                return {"ok": True, "bot": found.id, "closed": name}

            def status(self, _bot: SimpleNamespace) -> SimpleNamespace:
                return SimpleNamespace(model_dump=lambda mode="json": {"state": "running"})

        runtime = CursorRuntime(
            _Client(_Agents()),
            _settings(),
            store=_Store(),
            computers=_Computers(),
        )
        runtime.set_current_turn_context("bot_42", "run_99", "th_1")
        open_tool = runtime._custom_tools()["open_path"]
        launch_tool = runtime._custom_tools()["launch_app"]

        res_open = open_tool.execute({"path": "https://youtube.com"}, SimpleNamespace(tool_call_id="c_open"))
        self.assertEqual(res_open, {"ok": True, "bot": "bot_42", "path": "https://youtube.com"})

        res_launch = launch_tool.execute({"application": "chromium", "uri": "https://youtube.com"}, SimpleNamespace(tool_call_id="c_launch"))
        self.assertEqual(res_launch, {"ok": True, "bot": "bot_42", "app": "chromium", "uri": "https://youtube.com"})

        close_tool = runtime._custom_tools()["close_app"]
        res_close = close_tool.execute({"application": "chromium"}, SimpleNamespace(tool_call_id="c_close"))
        self.assertEqual(res_close, {"ok": True, "bot": "bot_42", "closed": "chromium"})

    def test_has_sent_message_in_turn_tracking(self) -> None:
        runtime = CursorRuntime(_Client(_Agents()), _settings())
        self.assertFalse(runtime.has_sent_message_in_turn("run_1"))
        runtime._messages_sent_in_turn.add("run_1")
        self.assertTrue(runtime.has_sent_message_in_turn("run_1"))
        runtime.clear_active_turn(run_id="run_1")
        self.assertFalse(runtime.has_sent_message_in_turn("run_1"))

    def test_send_message_sets_turn_tracking(self) -> None:
        bot = SimpleNamespace(id="bot_42", thread_id="th_1", name="test", workspace_id="ws_1")

        class _Store:
            def __init__(self) -> None:
                self.messages: list[dict[str, object]] = []

            def get_bot(self, bot_id: str) -> SimpleNamespace | None:
                return bot if bot_id == "bot_42" else None

            def append_bot_message(self, bot_obj: object, blocks: list[object], run_id: str | None = None) -> SimpleNamespace:
                msg = SimpleNamespace(id="msg_1", model_dump=lambda mode="json": {"id": "msg_1", "blocks": blocks})
                self.messages.append({"bot": bot_obj, "blocks": blocks, "run_id": run_id})
                return msg

        store = _Store()
        runtime = CursorRuntime(_Client(_Agents()), _settings(), store=store)
        runtime.set_current_turn_context("bot_42", "run_99", "th_1")
        tool = runtime._custom_tools()["send_message"]

        self.assertFalse(runtime.has_sent_message_in_turn("run_99"))
        res = tool.execute({"text": "Hello user"}, SimpleNamespace(tool_call_id="c_send"))
        self.assertTrue(res["ok"])
        self.assertEqual(res["message_id"], "msg_1")
        self.assertTrue(runtime.has_sent_message_in_turn("run_99"))
        self.assertEqual(len(store.messages), 1)


class CursorStreamAdapterTest(unittest.IsolatedAsyncioTestCase):
    async def test_stream_yields_product_events_and_maps_finished(self) -> None:
        class _Run:
            id = "cr-1"

            async def events(self):
                yield SimpleNamespace(
                    kind="interaction_update",
                    interaction_update=SimpleNamespace(type="text-delta", text="hi"),
                )

            async def wait(self):
                return SimpleNamespace(result="hi", status="finished")

            async def text(self):
                return "hi"

        class _Agent:
            async def send(self, prompt: str, opts: object) -> _Run:
                return _Run()

        runtime = CursorRuntime(_Client(_Agents()), _settings())
        runtime._agents["bc-1"] = _Agent()
        items: list[object] = []
        async for item in runtime.stream("hello", session_id="bc-1"):
            items.append(item)
        from artek_buddy.runtime import ProductStreamEvent, RunRecord

        self.assertTrue(items)
        self.assertIsInstance(items[0], ProductStreamEvent)
        self.assertEqual(items[0].type, "thread.message.updated")
        self.assertEqual(items[0].payload["delta"], "hi")
        self.assertIsInstance(items[-1], RunRecord)
        self.assertEqual(items[-1].status, "completed")
        self.assertEqual(items[-1].result, "hi")


class RuntimeSessionTest(unittest.IsolatedAsyncioTestCase):
    async def test_ensure_session_resumes_when_possible(self) -> None:
        agents = _Agents()
        runtime = CursorRuntime(_Client(agents), _settings())
        live = await runtime.ensure_session("bc-old", name="artek-buddy")
        self.assertEqual(live, "bc-old")
        self.assertEqual(agents.create_calls, 0)
        self.assertEqual(len(agents.resume_calls), 1)
        self.assertIsInstance(agents.resume_calls[0][1], AgentOptions)

    async def test_ensure_session_creates_after_resume_failure(self) -> None:
        agents = _Agents(
            resume_error=TypeError(
                "Object of type LocalAgentOptions is not JSON serializable"
            )
        )
        runtime = CursorRuntime(_Client(agents), _settings())
        live = await runtime.ensure_session("bc-old", name="artek-buddy")
        self.assertEqual(live, "bc-new")
        self.assertEqual(agents.create_calls, 1)
        self.assertIn("bc-new", runtime._agents)


if __name__ == "__main__":
    unittest.main()
