#!/usr/bin/env python3
"""Routine table against a throwaway TEST_DATABASE_URL. No Cursor calls."""

from __future__ import annotations

import sys
import unittest
from datetime import datetime, timedelta, timezone

from tests.pgutil import open_test_store


class RoutinesIntegrationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.store = open_test_store()
        cls.bot = cls.store.create_bot(name="routine-bot")

    @classmethod
    def tearDownClass(cls) -> None:
        store = getattr(cls, "store", None)
        bot = getattr(cls, "bot", None)
        if store is not None and bot is not None:
            store.delete_bot(bot.id)
        if store is not None:
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
        self.assertIn("routines", names)

    def test_create_list_update_delete(self) -> None:
        created = self.store.create_routine(
            self.bot.id,
            "Morning check",
            "Summarize overnight",
            "0 9 * * *",
            active=True,
        )
        self.assertTrue(created.id.startswith("rtn_"))
        self.assertTrue(created.active)
        self.assertIsNotNone(created.next_run_at)
        listed = {item.id: item for item in self.store.list_routines(self.bot.id)}
        self.assertIn(created.id, listed)
        paused = self.store.update_routine(created.id, active=False)
        assert paused is not None
        self.assertFalse(paused.active)
        self.assertIsNone(paused.next_run_at)
        self.assertTrue(self.store.delete_routine(created.id))
        self.assertIsNone(self.store.get_routine(created.id))

    def test_claim_due_holds_lease_until_ack(self) -> None:
        created = self.store.create_routine(
            self.bot.id,
            "Due now",
            "Wake",
            "* * * * *",
            active=True,
        )
        past = datetime.now(timezone.utc) - timedelta(minutes=2)
        with self.store._conn() as conn:
            conn.execute(
                "UPDATE routines SET next_run_at = %s WHERE id = %s",
                (past, created.id),
            )
            conn.commit()
        claimed = [item for item in self.store.claim_due_routines() if item.id == created.id]
        self.assertEqual(len(claimed), 1)
        self.assertIsNotNone(claimed[0].last_run_at)
        again = [item for item in self.store.claim_due_routines() if item.id == created.id]
        self.assertEqual(again, [])
        expired = datetime.now(timezone.utc) - timedelta(minutes=1)
        with self.store._conn() as conn:
            conn.execute(
                "UPDATE routines SET lease_until = %s WHERE id = %s",
                (expired, created.id),
            )
            conn.commit()
        reclaimed = [item for item in self.store.claim_due_routines() if item.id == created.id]
        self.assertEqual(len(reclaimed), 1)
        self.store.ack_routine(created.id)
        after_ack = [item for item in self.store.claim_due_routines() if item.id == created.id]
        self.assertEqual(after_ack, [])
        self.store.delete_routine(created.id)

    def test_invalid_cron_rejected(self) -> None:
        from artek_buddy.cron import CronError

        with self.assertRaises(CronError):
            self.store.create_routine(self.bot.id, "Bad", "nope", "often")


if __name__ == "__main__":
    if "--help" in sys.argv:
        print("Needs TEST_DATABASE_URL or make test-integration")
    unittest.main()
