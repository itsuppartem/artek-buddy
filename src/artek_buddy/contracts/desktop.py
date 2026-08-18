from __future__ import annotations

from typing import Protocol, TypedDict


class WindowState(TypedDict):
    minimized: bool
    maximized: bool
    full_screen: bool


class DesktopWindow(Protocol):
    async def close(self) -> None: ...
    async def minimize(self) -> None: ...
    async def toggle_maximize(self) -> None: ...
    async def state(self) -> WindowState: ...


class Desktop(Protocol):
    platform: str
    window: DesktopWindow
