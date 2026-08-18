from __future__ import annotations

import subprocess
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

from artek_buddy.computer.client import FakeSupervisorClient
from artek_buddy.computer.models import ComputerRecord
from artek_buddy.computer.screen import embeddable_screen_url, mint_novnc_url, resolve_novnc_target
from artek_buddy.computer.service import ComputerBusy, ComputerError, ComputerService
from artek_buddy.config import Settings
from artek_buddy.supervisor.logic import interactive_screen_command


def _settings(root: str) -> Settings:
    return Settings(
        cursor_api_key="crsr_test_key",
        agent_http_token="screen-secret",
        agent_cwd=str(Path(root) / "cwd"),
        agent_data_dir=str(Path(root) / "data"),
        sandbox_provider="fake",
        computer_takeover_ttl_seconds=900,
        computer_idle_seconds=600,
    )


def _record(**overrides: object) -> ComputerRecord:
    now = "2026-08-17T00:00:00Z"
    payload = dict(
        id="cmp_1",
        workspace_id="ws_default",
        scope="team",
        scope_key="team:ws_default",
        home_key="team-ws_default",
        home_revision="empty",
        kind="fake",
        provider_ref=None,
        state="stopped",
        control_holder="none",
        control_lease_id=None,
        control_lease_expires_at=None,
        control_bot_id=None,
        execution_run_id=None,
        execution_bot_id=None,
        execution_lease_expires_at=None,
        sleep_at=None,
        updated_at=now,
    )
    payload.update(overrides)
    return ComputerRecord(**payload)  # type: ignore[arg-type]


class _Store:
    def __init__(self, record: ComputerRecord, bot: SimpleNamespace) -> None:
        self.record = record
        self.bot = bot
        self.active: set[str] = set()

    def get_computer_for_bot(self, bot: object) -> ComputerRecord:
        return self.record

    def save_computer(self, record: ComputerRecord) -> ComputerRecord:
        self.record = record
        return record

    def busy_bot_name(self, computer: ComputerRecord, except_bot_id: str) -> str | None:
        if computer.execution_bot_id and computer.execution_bot_id != except_bot_id and computer.execution_bot_id in self.active:
            return "Other"
        return None

    def has_active_run(self, bot_id: str) -> bool:
        return bot_id in self.active

    def get_bot(self, bot_id: str) -> SimpleNamespace | None:
        return self.bot if bot_id == self.bot.id else None

    def update_bot(self, bot_id: str, computer_mode: str | None = None) -> SimpleNamespace:
        if computer_mode:
            self.bot.computer_mode = computer_mode
        return self.bot

    def ensure_computer(self, bot: SimpleNamespace) -> ComputerRecord:
        return self.record


class ScreenUrlTest(unittest.TestCase):
    def test_mint_and_resolve(self) -> None:
        url = mint_novnc_url("screen-secret", "127.0.0.1", 16080, interactive=False, now_ms=1_000)
        self.assertTrue(url.startswith("/novnc/"))
        self.assertIn("view_only=true", url)
        target = resolve_novnc_target(url, "screen-secret", now_ms=2_000)
        self.assertIsNotNone(target)
        assert target is not None
        self.assertEqual(target.hostname, "127.0.0.1")
        self.assertEqual(target.port, 16080)
        self.assertFalse(target.interactive)
        self.assertIn("view_only=true", target.path)

    def test_control_policy_cannot_be_flipped_by_query(self) -> None:
        url = mint_novnc_url("screen-secret", "127.0.0.1", 16081, interactive=False, now_ms=1_000)
        flipped = url.replace("view_only=true", "view_only=false")
        target = resolve_novnc_target(flipped, "screen-secret", now_ms=2_000)
        self.assertIsNotNone(target)
        assert target is not None
        self.assertIn("view_only=true", target.path)

    def test_bad_signature_and_raw_port_rejected(self) -> None:
        url = mint_novnc_url("screen-secret", "127.0.0.1", 16080, now_ms=1_000)
        sig = url.split("/")[5].split(".", 1)[1].split("/", 1)[0]
        self.assertIsNone(resolve_novnc_target(url.replace(sig, "a" * 43), "screen-secret", now_ms=2_000))
        self.assertIsNone(embeddable_screen_url("http://127.0.0.1:6080/embed.html"))
        self.assertIsNotNone(embeddable_screen_url(url))

    def test_expired_path_rejected(self) -> None:
        url = mint_novnc_url("screen-secret", "127.0.0.1", 16080, now_ms=1_000)
        self.assertIsNone(resolve_novnc_target(url, "screen-secret", now_ms=1_000 + 3_600_000 + 1))


class StatusMappingTest(unittest.TestCase):
    def test_screen_available_while_running_or_booting(self) -> None:
        running = _record(state="running").status_for("bot_1", "team")
        self.assertTrue(running.screen_available)
        booting = _record(state="booting").status_for("bot_1", "team")
        self.assertTrue(booting.screen_available)
        stopped = _record(state="stopped").status_for("bot_1", "dedicated")
        self.assertFalse(stopped.screen_available)
        self.assertEqual(stopped.mode, "dedicated")


class SupervisorLogicTest(unittest.TestCase):
    def test_interactive_screen_requires_token(self) -> None:
        with self.assertRaises(ValueError):
            interactive_screen_command(True, None)
        stop = interactive_screen_command(False, None)
        self.assertIn("pgrep -x x11vnc", stop)
        self.assertIn("pgrep -x websockify", stop)
        self.assertIn("kill", stop)
        start = interactive_screen_command(True, "lease_1")
        self.assertIn("5901", start)
        self.assertIn("6081", start)
        self.assertIn("lease_1", start)
        self.assertIn("setsid", start)
        self.assertIn("nohup", start)
        self.assertIn("-noxinerama", start)
        self.assertIn("-threads", start)
        self.assertNotIn("&;", start)
        self.assertNotIn("pkill -f", start)
        self.assertNotIn("pkill -f", stop)
        parsed = subprocess.run(["bash", "-n", "-c", start], capture_output=True, text=True)
        self.assertEqual(parsed.returncode, 0, parsed.stderr)
        parsed_stop = subprocess.run(["bash", "-n", "-c", stop], capture_output=True, text=True)
        self.assertEqual(parsed_stop.returncode, 0, parsed_stop.stderr)


class ComputerServiceTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory(prefix="artek-computer-")
        self.bot = SimpleNamespace(id="bot_1", name="Chief", computer_mode="team", workspace_id="ws_default")
        self.store = _Store(_record(), self.bot)
        self.client = FakeSupervisorClient()
        self.service = ComputerService(self.store, _settings(self.tmp.name), self.client)  # type: ignore[arg-type]

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_boot_takeover_release_heartbeat(self) -> None:
        status = self.service.boot(self.bot)  # type: ignore[arg-type]
        self.assertEqual(status.state, "running")
        self.assertTrue(status.screen_available)
        self.assertIn("provision", [call[0] for call in self.client.calls])
        lease = self.service.takeover(self.bot)  # type: ignore[arg-type]
        self.assertTrue(lease.lease_id.startswith("lease_"))
        self.assertEqual(self.store.record.control_holder, "user")
        screen = self.service.screen_url(self.bot)  # type: ignore[arg-type]
        self.assertIsNotNone(screen.url)
        assert screen.url is not None
        self.assertTrue(screen.url.startswith("/novnc/"))
        self.assertIn("/control/", screen.url)
        self.service.heartbeat(self.bot)  # type: ignore[arg-type]
        self.assertIsNotNone(self.store.record.sleep_at)
        released = self.service.release(self.bot)  # type: ignore[arg-type]
        self.assertEqual(released.control_holder, "bot")
        view = self.service.screen_url(self.bot)  # type: ignore[arg-type]
        assert view.url is not None
        self.assertIn("/view/", view.url)

    def test_expired_lease_drops_control(self) -> None:
        self.service.boot(self.bot)  # type: ignore[arg-type]
        self.service.takeover(self.bot)  # type: ignore[arg-type]
        past = datetime.now(timezone.utc) - timedelta(minutes=1)
        self.store.record.control_lease_expires_at = past.strftime("%Y-%m-%dT%H:%M:%SZ")
        status = self.service.status(self.bot)  # type: ignore[arg-type]
        self.assertNotEqual(status.control_holder, "user")

    def test_team_busy_is_409(self) -> None:
        other = SimpleNamespace(id="bot_2", name="Other", computer_mode="team", workspace_id="ws_default")
        self.store.record.execution_bot_id = "bot_2"
        self.store.active.add("bot_2")
        with self.assertRaises(ComputerBusy):
            self.service.boot(self.bot)  # type: ignore[arg-type]
        self.store.active.clear()
        status = self.service.boot(self.bot)  # type: ignore[arg-type]
        self.assertEqual(status.state, "running")

    def test_input_requires_lease(self) -> None:
        self.service.boot(self.bot)  # type: ignore[arg-type]
        with self.assertRaises(ComputerError):
            self.service.send_input(self.bot, "click", {"x": 1, "y": 1})  # type: ignore[arg-type]
        self.service.takeover(self.bot)  # type: ignore[arg-type]
        self.service.send_input(self.bot, "click", {"x": 10, "y": 10})  # type: ignore[arg-type]
        self.assertEqual(self.client.calls[-1][0], "input")

    def test_screen_url_stays_on_view_when_control_stack_fails(self) -> None:
        self.service.boot(self.bot)  # type: ignore[arg-type]
        self.service.takeover(self.bot)  # type: ignore[arg-type]

        def boom(*_args: object, **_kwargs: object) -> object:
            raise RuntimeError("screen-mode failed")

        self.client.screen_mode = boom  # type: ignore[method-assign]
        screen = self.service.screen_url(self.bot)  # type: ignore[arg-type]
        assert screen.url is not None
        self.assertIn("/view/", screen.url)

    def test_open_path_auto_boots_and_calls_act(self) -> None:
        self.assertEqual(self.store.record.state, "stopped")
        res = self.service.open_path(self.bot, "https://youtube.com")  # type: ignore[arg-type]
        self.assertTrue(res["ok"])
        self.assertEqual(self.store.record.state, "running")
        last_call = self.client.calls[-1]
        self.assertEqual(last_call[0], "act")
        self.assertEqual(last_call[1], [{"kind": "open", "path": "https://youtube.com"}])

    def test_launch_app_auto_boots_and_calls_act(self) -> None:
        self.assertEqual(self.store.record.state, "stopped")
        res = self.service.launch_app(self.bot, "chromium", uri="https://youtube.com")  # type: ignore[arg-type]
        self.assertTrue(res["ok"])
        self.assertEqual(self.store.record.state, "running")
        last_call = self.client.calls[-1]
        self.assertEqual(last_call[0], "act")
        self.assertEqual(last_call[1], [{"kind": "launch", "name": "chromium", "uri": "https://youtube.com"}])


    def test_action_command_open_url_and_files(self) -> None:
        from artek_buddy.supervisor.logic import action_command

        cmd_url = action_command([{"kind": "open", "path": "https://youtube.com"}])
        self.assertIn("nohup artek-browser 'https://youtube.com'", cmd_url)

        cmd_domain = action_command([{"kind": "open", "path": "youtube.com"}])
        self.assertIn("nohup artek-browser 'https://youtube.com'", cmd_domain)

        cmd_file = action_command([{"kind": "open", "path": "/home/artek/notes.txt"}])
        self.assertIn("nohup xdg-open '/home/artek/notes.txt'", cmd_file)

    def test_action_command_launch_app(self) -> None:
        from artek_buddy.supervisor.logic import action_command

        cmd_chrome = action_command([{"kind": "launch", "application": "chromium", "uri": "https://youtube.com"}])
        self.assertIn("nohup 'artek-browser' 'https://youtube.com'", cmd_chrome)

        cmd_generic = action_command([{"kind": "launch", "application": "xterm"}])
        self.assertIn("nohup 'xterm'", cmd_generic)

    def test_close_app_does_not_boot_a_stopped_box(self) -> None:
        self.assertEqual(self.store.record.state, "stopped")
        res = self.service.close_app(self.bot, "chromium")  # type: ignore[arg-type]
        self.assertEqual(res, {"ok": True, "closed": "chromium", "state": "stopped"})
        self.assertEqual(self.store.record.state, "stopped")
        self.assertEqual(self.client.calls, [])

    def test_close_app_on_running_box_sends_close(self) -> None:
        self.service.boot(self.bot)  # type: ignore[arg-type]
        res = self.service.close_app(self.bot, "chromium")  # type: ignore[arg-type]
        self.assertTrue(res["ok"])
        last_call = self.client.calls[-1]
        self.assertEqual(last_call[0], "act")
        self.assertEqual(last_call[1], [{"kind": "close", "name": "chromium"}])

    def test_action_command_close_browser(self) -> None:
        from artek_buddy.supervisor.logic import action_command

        cmd = action_command([{"kind": "close", "application": "chromium"}])
        self.assertIn("xdotool search --onlyvisible --class", cmd)
        self.assertIn("windowkill", cmd)
        self.assertIn("pkill -x", cmd)
        self.assertNotIn("pkill -f", cmd)
        parsed = subprocess.run(["bash", "-n", "-c", cmd], capture_output=True, text=True)
        self.assertEqual(parsed.returncode, 0, parsed.stderr)


if __name__ == "__main__":
    unittest.main()
