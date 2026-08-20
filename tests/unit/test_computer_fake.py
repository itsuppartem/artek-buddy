from __future__ import annotations

import time

from artek_buddy.computer.client import FakeSupervisorClient
from artek_buddy.computer.service import wipe_computer_home


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


def test_fake_running_box_counts_as_alive_without_ports() -> None:
    from artek_buddy.computer.service import ComputerService
    from artek_buddy.config import Settings

    client = FakeSupervisorClient()
    box = client.provision("bot_1", "team-ws")
    service = ComputerService(
        store=None,
        settings=Settings(
            agent_http_token="ci-host-token-aabbccddeeff001122334455",
            sandbox_provider="fake",
            cursor_api_key="",
        ),
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
    from artek_buddy.computer.service import ComputerError
    import pytest

    with pytest.raises(ComputerError):
        wipe_computer_home(tmp_path, "../escape")
    path = wipe_computer_home(tmp_path, "team-ws")
    assert path == (tmp_path / "homes" / "team-ws").resolve()
    (path / "cookie").write_text("x")
    wiped = wipe_computer_home(tmp_path, "team-ws")
    assert not (wiped / "cookie").exists()
