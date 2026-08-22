from __future__ import annotations

import time

from artek_buddy.computer.client import FakeSupervisorClient
from artek_buddy.computer.models import ComputerRecord
from artek_buddy.computer.service import ComputerService, wipe_computer_home
from artek_buddy.config import Settings
from artek_buddy.contracts.domain import Bot


def test_fake_supervisor_provision_and_stop() -> None:
    client = FakeSupervisorClient()
    box = client.provision("bot_1", "team-ws")
    assert box.running is True
    assert box.id in client.boxes
    client.stop(box.id)
    assert client.boxes[box.id]["running"] is False


def test_fake_box_has_no_screen_ports() -> None:
    """Fake CI desktops do not listen on noVNC. Lying about ports mints a dead /novnc/ iframe."""
    client = FakeSupervisorClient()
    box = client.provision("bot_1", "team-ws")
    assert box.view_port is None
    assert box.control_port is None
    assert box.screen_url is None
    inspected = client.inspect(box.id)
    assert inspected.view_port is None
    assert inspected.control_port is None


def _settings() -> Settings:
    return Settings(
        agent_http_token="ci-host-token-aabbccddeeff001122334455",
        sandbox_provider="fake",
        cursor_api_key="",
    )


def _bot() -> Bot:
    return Bot(
        id="bot_1",
        workspace_id="ws",
        name="Box",
        title="",
        description="",
        instructions="",
        color="#E65707",
        notify_on_finish=True,
        pinned=False,
        archived_at=None,
        unread=False,
        parent_bot_id=None,
        thread_id="thr_1",
        preview="",
        status="idle",
        computer_mode="dedicated",
        updated_at="2026-08-20T00:00:00Z",
        created_at="2026-08-20T00:00:00Z",
    )


class _ComputerStore:
    def __init__(self, record: ComputerRecord) -> None:
        self.record = record

    def get_computer_for_bot(self, _bot: Bot) -> ComputerRecord:
        return self.record

    def busy_bot_name(self, _record: ComputerRecord, _bot_id: str) -> str | None:
        return None

    def save_computer(self, record: ComputerRecord) -> ComputerRecord:
        self.record = record
        return record


def test_stop_marks_computer_sleeping() -> None:
    """WINDOW.md Stop → Sleeping. `stopped` is Offline in the Settings power label."""
    client = FakeSupervisorClient()
    box = client.provision("bot_1", "home-box")
    record = ComputerRecord(
        id="cmp_1",
        workspace_id="ws",
        scope="dedicated",
        scope_key="bot_1",
        home_key="home-box",
        home_revision=None,
        kind="fake",
        provider_ref=box.id,
        state="running",
        control_holder="user",
        control_lease_id="lease",
        control_lease_expires_at="2099-01-01T00:00:00Z",
        control_bot_id="bot_1",
        execution_run_id=None,
        execution_bot_id="bot_1",
        execution_lease_expires_at=None,
        sleep_at=None,
        updated_at="2026-08-20T00:00:00Z",
    )
    service = ComputerService(store=_ComputerStore(record), settings=_settings(), client=client)
    status = service.stop(_bot())
    assert status.state == "suspended"
    assert client.boxes[box.id]["running"] is False


def test_fake_running_box_counts_as_alive_without_ports() -> None:
    client = FakeSupervisorClient()
    box = client.provision("bot_1", "team-ws")
    service = ComputerService(
        store=None,
        settings=_settings(),
        client=client,
    )
    assert service._box_alive(box.id) is True


def test_fetch_novnc_caps_urlopen_timeout_to_deadline(monkeypatch) -> None:
    from artek_buddy.computer import proxy

    monkeypatch.setattr(proxy, "SCREEN_STARTUP_RETRY_SECONDS", 1.0)
    timeouts: list[float] = []

    def fake_urlopen(_request, timeout=None):
        timeouts.append(timeout)
        raise OSError("timed out")

    monkeypatch.setattr(proxy.urllib.request, "urlopen", fake_urlopen)
    started = time.monotonic()
    response = proxy.fetch_novnc("http://127.0.0.1:16080/embed.html", "GET")
    assert response.status_code == 502
    assert timeouts
    assert all(t is not None and t <= 1.05 for t in timeouts)
    assert time.monotonic() - started < 3


def test_wipe_computer_home_rejects_escape(tmp_path) -> None:
    import pytest

    from artek_buddy.computer.service import ComputerError

    with pytest.raises(ComputerError):
        wipe_computer_home(tmp_path, "../escape")
    path = wipe_computer_home(tmp_path, "team-ws")
    assert path == (tmp_path / "homes" / "team-ws").resolve()
    (path / "cookie").write_text("x")
    wiped = wipe_computer_home(tmp_path, "team-ws")
    assert not (wiped / "cookie").exists()
