from __future__ import annotations

import unittest
from types import SimpleNamespace

from artek_buddy.bus import EventHub
from artek_buddy.contracts.events import ProductEvent, ProductEventType
from artek_buddy.stream import accumulate, map_cursor_event, tool_name


class StreamMapTest(unittest.TestCase):
    def test_text_delta(self) -> None:
        event = SimpleNamespace(
            kind="interaction_update",
            interaction_update=SimpleNamespace(type="text-delta", text="hel"),
        )
        mapped = map_cursor_event(event)
        self.assertEqual(mapped, [("thread.message.updated", {"delta": "hel", "kind": "text"})])
        self.assertEqual(accumulate("", mapped[0][1]), "hel")
        self.assertEqual(accumulate("hel", {"delta": "lo", "kind": "text"}), "hello")

    def test_tool_started(self) -> None:
        event = SimpleNamespace(
            kind="interaction_update",
            interaction_update=SimpleNamespace(
                type="tool-call-started",
                call_id="c1",
                tool_call={"name": "shell"},
            ),
        )
        mapped = map_cursor_event(event)
        self.assertEqual(mapped, [])

    def test_tool_name_nested(self) -> None:
        self.assertEqual(tool_name({"function": {"name": "read"}}), "read")
        self.assertEqual(tool_name({}), "tool")

    def test_remember_tool_completed_maps_to_meta(self) -> None:
        event = SimpleNamespace(
            kind="interaction_update",
            interaction_update=SimpleNamespace(
                type="tool-call-completed",
                call_id="c_rem",
                tool_call={"name": "remember", "args": {"path": "NOTES.md", "content": "fact"}},
            ),
        )
        mapped = map_cursor_event(event)
        self.assertEqual(mapped[0][0], "thread.meta")
        self.assertEqual(mapped[0][1]["text"], "Saved fact to NOTES.md")

    def test_subagent_tool_started_and_completed(self) -> None:
        event = SimpleNamespace(
            kind="interaction_update",
            interaction_update=SimpleNamespace(
                type="tool-call-started",
                call_id="c_sub",
                tool_call={"name": "run_subagent", "args": {"name": "scout", "task": "find info"}},
            ),
        )
        mapped = map_cursor_event(event)
        self.assertEqual(mapped[0][0], "thread.subagent")
        self.assertEqual(mapped[0][1]["name"], "scout")
        self.assertEqual(mapped[0][1]["status"], "running")

    def test_spawn_subagent_does_not_emit_a_placeholder_card(self) -> None:
        event = SimpleNamespace(
            kind="interaction_update",
            interaction_update=SimpleNamespace(
                type="tool-call-started",
                call_id="c_spawn",
                tool_call={"name": "spawn_subagent", "args": {"name": "scout", "task": "find info"}},
            ),
        )
        mapped = map_cursor_event(event)
        self.assertEqual(mapped, [])

    def test_spawn_bot_tool_completed(self) -> None:
        event = SimpleNamespace(
            kind="interaction_update",
            interaction_update=SimpleNamespace(
                type="tool-call-completed",
                call_id="c_spn",
                tool_call={"name": "spawn_bot", "args": {"name": "HelperBot", "title": "A helper"}},
            ),
        )
        mapped = map_cursor_event(event)
        self.assertEqual(mapped[0][0], "bot.spawned")
        self.assertEqual(mapped[0][1]["name"], "HelperBot")
        self.assertEqual(mapped[0][1]["status"], "created")

    def test_replace_assistant(self) -> None:
        content = SimpleNamespace(content=[SimpleNamespace(text="full")])
        event = SimpleNamespace(
            kind="sdk_message",
            sdk_message=SimpleNamespace(type="assistant", message=content),
        )
        mapped = map_cursor_event(event)
        self.assertTrue(mapped[0][1]["replace"])
        self.assertEqual(accumulate("old", mapped[0][1]), "full")

    def test_accumulate_keeps_longer_prefix(self) -> None:
        self.assertEqual(accumulate("Hello", {"text": "Hel", "replace": True}), "Hello")
        self.assertEqual(accumulate("Hel", {"text": "Hello", "replace": True}), "Hello")
        self.assertEqual(accumulate("Hello", {"delta": "!", "text": "Hello!"}), "Hello!")

    def test_thinking_is_suppressed(self) -> None:
        event = SimpleNamespace(
            kind="interaction_update",
            interaction_update=SimpleNamespace(type="thinking-delta", text="internal thought"),
        )
        self.assertEqual(map_cursor_event(event), [])

        sdk_event = SimpleNamespace(
            kind="sdk_message",
            sdk_message=SimpleNamespace(type="thinking", text="more thoughts"),
        )
        self.assertEqual(map_cursor_event(sdk_event), [])


class EventHubTest(unittest.TestCase):
    def test_replay_after(self) -> None:
        hub = EventHub()
        first = ProductEvent(
            id="evt_a",
            workspace_id="ws",
            thread_id="th",
            bot_id="bot",
            seq=1,
            type=ProductEventType.RUN_STARTED,
            created_at="2026-08-17T00:00:00Z",
            payload={},
            run_id="run_1",
        )
        second = first.model_copy(update={"id": "evt_b", "seq": 2})
        hub.publish(first)
        hub.publish(second)
        self.assertEqual([item.id for item in hub.replay("bot")], ["evt_a", "evt_b"])
        self.assertEqual([item.id for item in hub.replay("bot", after="evt_a")], ["evt_b"])
        self.assertEqual(hub.replay("missing"), [])


if __name__ == "__main__":
    unittest.main()
