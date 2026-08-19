#!/usr/bin/env python3
"""Memory tables against a throwaway TEST_DATABASE_URL. No Cursor calls."""

from __future__ import annotations

import sys
import unittest

from artek_buddy.memory import MemoryConflict, MemoryPathError, format_memory_context, wrap_turn_prompt
from artek_buddy.memory_hub import InMemoryGateway, MemoryHub
from tests.pgutil import open_test_store


class MemoryIntegrationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.store = open_test_store()
        cls.bot = cls.store.create_bot(name="memory-bot")

    @classmethod
    def tearDownClass(cls) -> None:
        store = getattr(cls, "store", None)
        bot = getattr(cls, "bot", None)
        if store is not None and bot is not None:
            store.delete_bot(bot.id)
        if store is not None:
            for document in store.list_memory(scope="user"):
                store.delete_memory(document.id)
            store.close()

    def test_table_exists(self) -> None:
        with self.store._conn() as conn:
            rows = conn.execute(
                """
                SELECT table_name FROM information_schema.tables
                WHERE table_schema = 'public'
                """
            ).fetchall()
            conn.commit()
        names = {row["table_name"] for row in rows}
        self.assertIn("memory_documents", names)
        self.assertIn("memory_revisions", names)
        self.assertIn("memory_entries", names)

    def test_create_list_update_delete(self) -> None:
        created = self.store.create_memory(
            "bot",
            "Likes short answers",
            bot_id=self.bot.id,
            path="MEMORY.md",
        )
        self.addCleanup(self.store.delete_memory, created.id)
        self.assertTrue(created.id.startswith("mem_"))
        self.assertEqual(created.revision, 1)
        listed = {item.id: item for item in self.store.list_memory(bot_id=self.bot.id)}
        self.assertIn(created.id, listed)
        updated = self.store.update_memory(created.id, "Likes short answers. Speaks Russian.")
        assert updated is not None
        self.assertEqual(updated.revision, 2)
        self.assertIn("Russian", updated.content)
        self.assertTrue(self.store.delete_memory(created.id))
        self.assertIsNone(self.store.get_memory(created.id))

    def test_user_memory_survives_bot_delete(self) -> None:
        other = self.store.create_bot(name="memory-gone")
        bot_doc = self.store.create_memory("bot", "bot only", bot_id=other.id)
        user_doc = self.store.create_memory("user", "owner fact", path="PROFILE.md")
        self.addCleanup(self.store.delete_memory, user_doc.id)
        self.assertTrue(self.store.delete_bot(other.id, delete_memories=True))
        self.assertIsNone(self.store.get_memory(bot_doc.id))
        kept = self.store.get_memory(user_doc.id)
        assert kept is not None
        self.assertEqual(kept.content, "owner fact")

    def test_duplicate_path_conflicts(self) -> None:
        first = self.store.create_memory("bot", "one", bot_id=self.bot.id, path="notes.md")
        self.addCleanup(self.store.delete_memory, first.id)
        with self.assertRaises(MemoryConflict):
            self.store.create_memory("bot", "two", bot_id=self.bot.id, path="notes.md")

    def test_bad_path_rejected(self) -> None:
        with self.assertRaises(MemoryPathError):
            self.store.create_memory("bot", "x", bot_id=self.bot.id, path="../etc")

    def test_agent_context_includes_bot_and_user(self) -> None:
        bot_doc = self.store.create_memory("bot", "bot fact", bot_id=self.bot.id, path="BOT.md")
        user_doc = self.store.create_memory("user", "user fact", path="USER.md")
        self.addCleanup(self.store.delete_memory, bot_doc.id)
        self.addCleanup(self.store.delete_memory, user_doc.id)
        prompt = wrap_turn_prompt(
            "what do you know?",
            format_memory_context(self.store.memory_for_agent(self.bot.id)),
        )
        self.assertIn("bot fact", prompt)
        self.assertIn("user fact", prompt)
        self.assertTrue(prompt.endswith("what do you know?"))

    def test_shelves_tone_format_and_expired_work(self) -> None:
        hub = MemoryHub(self.store, InMemoryGateway())
        tone = hub.capture("без эмодзи", kind="preference", bot_id=self.bot.id)
        fmt = hub.capture("пиши коротко", kind="preference", bot_id=self.bot.id)
        work = hub.capture("repo artek-buddy on main this week", kind="project", bot_id=self.bot.id)
        assert tone is not None and fmt is not None and work is not None
        self.addCleanup(self.store.delete_memory, tone.document_id)
        self.addCleanup(self.store.delete_memory, fmt.document_id)
        self.addCleanup(self.store.delete_memory, work.document_id)
        self.assertEqual(tone.slot, "tone")
        self.assertEqual(fmt.slot, "format")
        self.assertEqual(work.shelf, "work")
        self.assertIsNotNone(work.until)
        live = {entry.id: entry for entry in self.store.list_live_memory_entries(bot_id=self.bot.id)}
        self.assertEqual(live[tone.id].shelf, "owner")
        self.assertEqual(live[fmt.id].shelf, "owner")
        self.assertIn(work.id, live)
        with self.store._conn() as conn:
            conn.execute(
                "UPDATE memory_entries SET until = NOW() - INTERVAL '1 hour' WHERE id = %s",
                (work.id,),
            )
            conn.commit()
        hidden = {entry.id for entry in self.store.list_live_memory_entries(bot_id=self.bot.id)}
        self.assertNotIn(work.id, hidden)
        self.assertIn(tone.id, hidden)
        self.assertIn(fmt.id, hidden)

    def test_shared_entries_survive_other_bot_and_delete(self) -> None:
        reader = self.store.create_bot(name="memory-reader")
        writer = self.store.create_bot(name="memory-writer")
        hub = MemoryHub(self.store, InMemoryGateway())
        saved = hub.capture("Owner prefers tea", kind="preference", bot_id=writer.id)
        assert saved is not None
        self.addCleanup(self.store.delete_memory, saved.document_id)
        local = hub.capture(
            "This research uses Wikipedia only",
            kind="rule",
            scope="bot",
            bot_id=writer.id,
        )
        assert local is not None
        self.addCleanup(self.store.delete_memory, local.document_id)
        shared = {entry.text for entry in self.store.list_live_memory_entries(bot_id=reader.id)}
        self.assertIn("Owner prefers tea", shared)
        self.assertNotIn("This research uses Wikipedia only", shared)
        context = hub.context_for_turn(reader.id, "what tea does the owner like")
        assert context is not None
        self.assertIn("Owner prefers tea", context)
        self.assertTrue(self.store.delete_bot(writer.id, delete_memories=True))
        kept = {entry.text for entry in self.store.list_live_memory_entries(bot_id=reader.id)}
        self.assertIn("Owner prefers tea", kept)
        self.assertNotIn("This research uses Wikipedia only", kept)
        self.store.delete_bot(reader.id, delete_memories=True)


if __name__ == "__main__":
    if "--help" in sys.argv:
        print("Needs TEST_DATABASE_URL or make test-integration")
    unittest.main()
