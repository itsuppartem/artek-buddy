from __future__ import annotations

from artek_buddy.contracts.domain import Device
from artek_buddy.owner_clients import OWNER_WEB_ERROR, has_desktop_owner_client


def _device(platform: str, revoked: str | None = None) -> Device:
    return Device(
        id="dev_1",
        name="x",
        platform=platform,
        created_at="2026-01-01T00:00:00Z",
        revoked_at=revoked,
    )


def test_web_only_devices_are_not_this_pc() -> None:
    assert has_desktop_owner_client([]) is False
    assert has_desktop_owner_client([_device("web")]) is False
    assert has_desktop_owner_client([_device("ios"), _device("iphone")]) is False
    assert has_desktop_owner_client([_device("linux", revoked="2026-01-02T00:00:00Z")]) is False
    assert OWNER_WEB_ERROR.startswith("This-PC files need the Linux app")


def test_linux_device_keeps_this_pc() -> None:
    assert has_desktop_owner_client([_device("web"), _device("linux")]) is True
    assert has_desktop_owner_client([_device("darwin")]) is True
