from __future__ import annotations

import unittest

from artek_buddy.contracts import (
    CreateMemoryInput,
    MarkdownExport,
    MemoryDocument,
    MemoryScope,
    MemoryUpdateInput,
    PROCEDURES_BY_NAME,
)
from artek_buddy.memory import (
    MemoryPathError,
    export_markdown,
    format_memory_context,
    normalize_memory_path,
    wrap_turn_prompt,
)


class MemoryContractTest(unittest.TestCase):
    def test_memory_procedures_implemented(self) -> None:
        for name in (
            "memory.list",
            "memory.create",
            "memory.update",
            "memory.remove",
            "memory.export_markdown",
        ):
            self.assertTrue(PROCEDURES_BY_NAME[name].implemented, name)
        self.assertEqual(PROCEDURES_BY_NAME["memory.list"].path, "/v1/memory")
        self.assertEqual(PROCEDURES_BY_NAME["memory.create"].method, "POST")
        self.assertEqual(PROCEDURES_BY_NAME["memory.update"].path, "/v1/memory/{document_id}")
        self.assertEqual(PROCEDURES_BY_NAME["memory.export_markdown"].output_model, "MarkdownExport")

    def test_document_and_input_shapes(self) -> None:
        created = CreateMemoryInput.model_validate(
            {"scope": "bot", "bot_id": "bot_1", "content": "Likes tea"}
        )
        self.assertEqual(created.path, "MEMORY.md")
        self.assertEqual(created.scope, MemoryScope.bot)
        document = MemoryDocument.model_validate(
            {
                "id": "mem_1",
                "scope": "user",
                "bot_id": None,
                "path": "MEMORY.md",
                "content": "Owner is Artem",
                "revision": 2,
                "updated_at": "2026-08-17T00:00:00Z",
            }
        )
        self.assertEqual(document.scope, MemoryScope.user)
        self.assertEqual(MemoryUpdateInput.model_validate({"content": "x"}).content, "x")
        self.assertEqual(MarkdownExport.model_validate({"markdown": "# A"}).markdown, "# A")


class MemoryContextTest(unittest.TestCase):
    def test_normalize_path(self) -> None:
        self.assertEqual(normalize_memory_path(""), "MEMORY.md")
        self.assertEqual(normalize_memory_path(" notes/foo.md "), "notes/foo.md")
        with self.assertRaises(MemoryPathError):
            normalize_memory_path("../secret")
        with self.assertRaises(MemoryPathError):
            normalize_memory_path("/etc/passwd")

    def test_wrap_leaves_chat_text_outside_memory(self) -> None:
        self.assertEqual(wrap_turn_prompt("hello", None), "hello")
        wrapped = wrap_turn_prompt("hello", "<durable_memory>\nfact\n</durable_memory>")
        self.assertTrue(wrapped.endswith("hello"))
        self.assertIn("<durable_memory>", wrapped)

    def test_wrap_adds_reply_and_parallel_context(self) -> None:
        text = wrap_turn_prompt(
            "also sine 100",
            None,
            reply_excerpt="here are the headlines",
            reply_role="bot",
            parallel=True,
        )
        self.assertIn("subagent", text)
        self.assertIn("here are the headlines", text)
        self.assertTrue(text.endswith("also sine 100"))

    def test_wrap_lead_lists_workers(self) -> None:
        from artek_buddy.memory import format_subagent_context

        context = format_subagent_context(
            [
                {
                    "id": "sub_b",
                    "index": 2,
                    "name": "news",
                    "status": "running",
                    "task": "find headlines",
                },
                {
                    "id": "sub_a",
                    "index": 1,
                    "name": "sine",
                    "status": "queued",
                    "task": "play a tone",
                },
            ]
        )
        assert context is not None
        self.assertLess(context.index("1. sine"), context.index("2. news"))
        text = wrap_turn_prompt("what about the second?", None, role="lead", subagent_context=context)
        self.assertIn("spawn_subagent", text)
        self.assertIn("inspect_subagent", text)
        self.assertIn("steer_subagent", text)
        self.assertIn("close_app", text)
        self.assertIn("2. news", text)
        self.assertTrue(text.endswith("what about the second?"))

    def test_wrap_passes_lead_corrections_to_a_worker(self) -> None:
        from artek_buddy.memory import format_subagent_context

        context = format_subagent_context(
            [
                {
                    "id": "sub_2",
                    "index": 2,
                    "name": "news",
                    "status": "running",
                    "task": "find headlines",
                    "clarifications": "only Hacker News",
                }
            ]
        )
        assert context is not None
        self.assertIn("only Hacker News", context)
        text = wrap_turn_prompt(
            "find headlines",
            None,
            role="subagent",
            clarifications="only Hacker News",
            steer=True,
        )
        self.assertIn("only Hacker News", text)
        self.assertIn("correction", text)
        self.assertTrue(text.endswith("find headlines"))

    def test_format_injects_newest_first_and_caps_bytes(self) -> None:
        docs = [
            MemoryDocument(
                id="mem_old",
                scope=MemoryScope.user,
                bot_id=None,
                path="PROFILE.md",
                content="old fact",
                revision=1,
                updated_at="2026-08-01T00:00:00Z",
            ),
            MemoryDocument(
                id="mem_new",
                scope=MemoryScope.bot,
                bot_id="bot_1",
                path="MEMORY.md",
                content="new fact",
                revision=3,
                updated_at="2026-08-17T00:00:00Z",
            ),
        ]
        text = format_memory_context(docs)
        assert text is not None
        self.assertIn("<durable_memory>", text)
        self.assertLess(text.index("bot: MEMORY.md"), text.index("user: PROFILE.md"))
        self.assertIn("new fact", text)
        tiny = format_memory_context(docs, max_bytes=80)
        assert tiny is not None
        self.assertLessEqual(len(tiny.encode("utf-8")), 80)

    def test_export_markdown(self) -> None:
        docs = [
            MemoryDocument(
                id="mem_1",
                scope=MemoryScope.bot,
                bot_id="bot_1",
                path="MEMORY.md",
                content="prefers dark mode",
                revision=1,
                updated_at="2026-08-17T00:00:00Z",
            )
        ]
        self.assertEqual(export_markdown(docs), "# MEMORY.md\n\nprefers dark mode")
        self.assertEqual(export_markdown([]), "")


if __name__ == "__main__":
    unittest.main()
