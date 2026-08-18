#!/usr/bin/env python3
"""Computer lifecycle against throwaway Postgres. Uses the fake supervisor."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from artek_buddy.computer.client import FakeSupervisorClient
from artek_buddy.computer.service import ComputerBusy, ComputerService
from artek_buddy.config import Settings
from tests.pgutil import open_test_store


class ComputerIntegrationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.store = open_test_store()
        cls.tmp = tempfile.TemporaryDirectory(prefix="artek-computer-int-")

    @classmethod
    def tearDownClass(cls) -> None:
        cls.tmp.cleanup()
        store = getattr(cls, "store", None)
        if store is not None:
            store.close()

    def _service(self) -> tuple[ComputerService, FakeSupervisorClient]:
        client = FakeSupervisorClient()
        settings = Settings(
            cursor_api_key="crsr_test_key",
            agent_http_token="screen-secret",
            agent_cwd=str(Path(self.tmp.name) / "cwd"),
            agent_data_dir=str(Path(self.tmp.name) / "data"),
            sandbox_provider="fake",
        )
        return ComputerService(self.store, settings, client), client

    def test_boot_takeover_release_heartbeat(self) -> None:
        bot = self.store.create_bot(name="computer-int")
        self.addCleanup(self.store.delete_bot, bot.id)
        service, client = self._service()
        status = service.boot(bot)
        self.assertEqual(status.state, "running")
        self.assertTrue(status.screen_available)
        self.assertTrue(any(call[0] == "provision" for call in client.calls))
        lease = service.takeover(bot)
        self.assertTrue(lease.lease_id)
        self.assertEqual(service.status(bot).control_holder, "user")
        screen = service.screen_url(bot)
        self.assertIsNotNone(screen.url)
        assert screen.url is not None
        self.assertTrue(screen.url.startswith("/novnc/"))
        self.assertIn("/control/", screen.url)
        service.heartbeat(bot)
        record = self.store.get_computer_for_bot(bot)
        self.assertIsNotNone(record.sleep_at)
        released = service.release(bot)
        self.assertEqual(released.control_holder, "bot")
        view = service.screen_url(bot)
        assert view.url is not None
        self.assertIn("/view/", view.url)

    def test_team_busy_when_another_bot_is_running(self) -> None:
        first = self.store.create_bot(name="team-busy-a")
        second = self.store.create_bot(name="team-busy-b")
        self.addCleanup(self.store.delete_bot, first.id)
        self.addCleanup(self.store.delete_bot, second.id)
        service, _client = self._service()
        service.boot(first)
        self.store.begin_turn(first, "hold the box")
        with self.assertRaises(ComputerBusy) as raised:
            service.boot(second)
        self.assertEqual(raised.exception.name, first.name)

    def test_snapshot_row_is_real(self) -> None:
        bot = self.store.create_bot(name="computer-snapshot", computer_mode="dedicated")
        self.addCleanup(self.store.delete_bot, bot.id)
        record = self.store.get_computer_for_bot(bot)
        self.assertEqual(record.state, "stopped")
        self.assertEqual(record.scope, "dedicated")
        status = record.status_for(bot.id, bot.computer_mode)
        self.assertFalse(status.screen_available)
        self.assertEqual(status.kind, "docker")


if __name__ == "__main__":
    unittest.main()
