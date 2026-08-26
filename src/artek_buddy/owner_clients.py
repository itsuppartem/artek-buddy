from __future__ import annotations

from artek_buddy.contracts.domain import Device

WEB_PLATFORMS = frozenset({"web", "ios", "android", "iphone", "ipad", "phone"})
OWNER_WEB_ERROR = "This-PC files need the Linux app, not the phone browser."


def has_desktop_owner_client(devices: list[Device]) -> bool:
    return any(
        not device.revoked_at and device.platform.strip().lower() not in WEB_PLATFORMS
        for device in devices
    )
