#!/usr/bin/env python3
"""History tables against a throwaway TEST_DATABASE_URL. No Cursor calls."""

from __future__ import annotations

import sys
import unittest

from tests.pgutil import open_test_store


class HistoryIntegrationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.store = open_test_store()

    @classmethod
    def tearDownClass(cls) -> None:
        store = getattr(cls, "store", None)
        if store is not None:
            store.close()

    def test_tables_exist(self) -> None:
        with self.store._conn() as conn:
            rows = conn.execute(
                """
                SELECT table_name FROM information_schema.tables
                WHERE table_schema = 'public'
                ORDER BY table_name
                """
            ).fetchall()
            conn.commit()
        names = {row["table_name"] for row in rows}
        for table in (
            "workspaces",
            "bots",
            "threads",
            "messages",
            "runs",
            "schema_migrations",
            "memory_documents",
            "memory_revisions",
            "computers",
        ):
            self.assertIn(table, names)

    def test_seed_and_message_seq(self) -> None:
        bot = self.store.create_bot(name="integration-test")
        self.addCleanup(self.store.delete_bot, bot.id)
        self.assertTrue(bot.id)
        self.assertTrue(bot.thread_id)
        first, run = self.store.begin_turn(bot, "integration user")
        self.assertEqual(first.role.value if hasattr(first.role, "value") else first.role, "user")
        self.assertEqual(run.status.value if hasattr(run.status, "value") else run.status, "running")
        second, run = self.store.finish_turn(bot, run, "integration bot", "completed")
        self.assertEqual(second.seq, first.seq + 1)
        page = self.store.page_messages(bot.thread_id, limit=50)
        seqs = [item.seq for item in page.messages]
        self.assertIn(first.seq, seqs)
        self.assertIn(second.seq, seqs)

    def test_delete_bot_removes_history(self) -> None:
        bot = self.store.create_bot(name="integration-delete")
        self.store.begin_turn(bot, "gone")
        self.assertTrue(self.store.delete_bot(bot.id))
        self.assertIsNone(self.store.get_bot(bot.id))
        page = self.store.page_messages(bot.thread_id, limit=50)
        self.assertEqual(page.messages, [])
        self.assertFalse(self.store.delete_bot(bot.id))

    def test_bot_lifecycle_archive_duplicate_update(self) -> None:
        bot = self.store.create_bot(name="lifecycle-bot", title="Original Title")
        self.addCleanup(lambda: self.store.delete_bot(bot.id))

        # Update bot
        updated = self.store.update_bot(
            bot.id,
            title="New Title",
            pinned=True,
            instructions="Custom prompt",
            unread=True,
        )
        self.assertIsNotNone(updated)
        self.assertEqual(updated.title, "New Title")
        self.assertTrue(updated.pinned)
        self.assertTrue(updated.unread)

        # Archive bot
        archived = self.store.archive_bot(bot.id)
        self.assertIsNotNone(archived)
        self.assertIsNotNone(archived.archived_at)

        # list_bots should exclude archived
        active_bots = self.store.list_bots()
        self.assertNotIn(bot.id, [b.id for b in active_bots])

        # list_archived_bots should include archived
        archived_bots = self.store.list_archived_bots()
        self.assertIn(bot.id, [b.id for b in archived_bots])

        # Restore bot
        restored = self.store.restore_bot(bot.id)
        self.assertIsNotNone(restored)
        self.assertIsNone(restored.archived_at)

        # Duplicate bot
        duplicated = self.store.duplicate_bot(bot.id)
        self.addCleanup(lambda: self.store.delete_bot(duplicated.id))
        self.assertEqual(duplicated.name, "lifecycle-bot (Copy)")
        self.assertEqual(duplicated.title, "New Title")
        self.assertEqual(duplicated.instructions, "Custom prompt")

    def test_delete_bot_preserves_memories_when_requested(self) -> None:
        bot = self.store.create_bot(name="memory-preserve-bot")
        doc = self.store.create_memory("bot", "Important note", bot_id=bot.id, path="NOTES.md")
        self.assertEqual(doc.scope, "bot")

        # Delete with delete_memories=False
        self.assertTrue(self.store.delete_bot(bot.id, delete_memories=False))
        user_docs = self.store.list_memory()
        matching = [d for d in user_docs if "Important note" in d.content]
        self.assertTrue(len(matching) >= 1)
        self.assertEqual(matching[0].scope, "user")
        self.assertIn("bots/memory-preserve-bot", matching[0].path)
        # Cleanup preserved memory
        for m in matching:
            self.store.delete_memory(m.id)

    def test_reply_inbox_and_subagents(self) -> None:
        bot = self.store.create_bot(name="lead-inbox")
        self.addCleanup(self.store.delete_bot, bot.id)
        first, run = self.store.begin_turn(bot, "find news")
        queued = self.store.append_user_message(bot, "sine 100", reply_to_id=first.id)
        self.assertEqual(queued.reply_to_id, first.id)
        self.assertIsNotNone(queued.reply_to)
        self.assertIn("find news", queued.reply_to.excerpt)
        self.store.enqueue_inbox(bot.id, queued.id, "sine 100", reply_to_id=first.id)
        self.assertEqual(self.store.inbox_count(bot.id), 1)
        self.assertEqual(self.store.active_run_count(bot.id), 1)
        worker = self.store.create_subagent(bot, name="news", task="find headlines", parent_run_id=run.id)
        self.assertEqual(worker.index, 1)
        self.assertEqual(self.store.resolve_subagent(bot.id, "1").id, worker.id)
        self.assertEqual(self.store.resolve_subagent(bot.id, "news").id, worker.id)
        self.store.update_subagent(worker.id, status="running", thinking="opening the browser")
        found = self.store.get_subagent(worker.id)
        self.assertEqual(found.status, "running")
        self.assertEqual(found.thinking, "opening the browser")
        noted = self.store.append_clarification(worker.id, "only Hacker News")
        self.assertIsNotNone(noted)
        self.assertEqual(noted.clarifications, "only Hacker News")
        again = self.store.append_clarification(worker.id, "skip sports")
        self.assertEqual(again.clarifications, "only Hacker News\nskip sports")
        items = self.store.drain_inbox(bot.id)
        self.assertEqual(items[0]["text"], "sine 100")
        self.assertEqual(self.store.inbox_count(bot.id), 0)
        self.store.finish_turn(bot, run, "started the news worker", "completed")
        follow = self.store.begin_run(bot, trigger="follow_up")
        self.assertEqual(follow.trigger, "follow_up")
        self.assertTrue(self.store.has_active_run(bot.id))


if __name__ == "__main__":
    if "--help" in sys.argv:
        print("Needs TEST_DATABASE_URL or make test-integration")
    unittest.main()
