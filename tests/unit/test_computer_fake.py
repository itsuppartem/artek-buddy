from __future__ import annotations

from artek_buddy.computer.client import FakeSupervisorClient
from artek_buddy.computer.service import wipe_computer_home


def test_fake_supervisor_provision_and_stop() -> None:
    client = FakeSupervisorClient()
    box = client.provision("bot_1", "team-ws")
    assert box.running is True
    assert box.id in client.boxes
    client.stop(box.id)
    assert client.boxes[box.id]["running"] is False


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
