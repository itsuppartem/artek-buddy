from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import patch

from artek_buddy.worker import run_once


class _Store:
    def __init__(self, routines: list[SimpleNamespace]) -> None:
        self.routines = routines
        self.acked: list[str] = []
        self.rescheduled: list[str] = []

    def claim_due_routines(self) -> list[SimpleNamespace]:
        return list(self.routines)

    def ack_routine(self, routine_id: str) -> None:
        self.acked.append(routine_id)

    def reschedule_routine(self, routine_id: str, when: str) -> None:
        self.rescheduled.append(routine_id)

    def due_idle_computer_bots(self) -> list[str]:
        return []


class WorkerAckTest(unittest.TestCase):
    def test_success_and_busy_ack(self) -> None:
        store = _Store([SimpleNamespace(id="rtn_ok", bot_id="bot_1", prompt="wake")])
        with patch("artek_buddy.worker.wake_routine", return_value=200):
            self.assertEqual(run_once(store, "http://127.0.0.1:9", "token"), 1)
        self.assertEqual(store.acked, ["rtn_ok"])
        self.assertEqual(store.rescheduled, [])

        store = _Store([SimpleNamespace(id="rtn_busy", bot_id="bot_1", prompt="wake")])
        with patch("artek_buddy.worker.wake_routine", return_value=409):
            self.assertEqual(run_once(store, "http://127.0.0.1:9", "token"), 0)
        self.assertEqual(store.acked, ["rtn_busy"])

    def test_failure_reschedules_without_ack(self) -> None:
        store = _Store([SimpleNamespace(id="rtn_fail", bot_id="bot_1", prompt="wake")])
        with patch("artek_buddy.worker.wake_routine", return_value=500):
            self.assertEqual(run_once(store, "http://127.0.0.1:9", "token"), 0)
        self.assertEqual(store.acked, [])
        self.assertEqual(store.rescheduled, ["rtn_fail"])


if __name__ == "__main__":
    unittest.main()
