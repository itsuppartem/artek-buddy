from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

CLIENT_DIR = Path(__file__).resolve().parents[2] / "client"
TRAY = CLIENT_DIR / "tray.py"
if str(CLIENT_DIR) not in sys.path:
    sys.path.insert(0, str(CLIENT_DIR))


class FakeMenu:
    def __init__(self) -> None:
        self.items: list[FakeMenuItem] = []
        self.shown = False

    def append(self, item: FakeMenuItem) -> None:
        self.items.append(item)

    def show_all(self) -> None:
        self.shown = True


class FakeMenuItem:
    def __init__(self, *, label: str) -> None:
        self.label = label
        self.callback = None

    def connect(self, signal: str, callback) -> None:
        assert signal == "activate"
        self.callback = callback


class FakeGtk:
    Menu = FakeMenu
    MenuItem = FakeMenuItem


class FakeIndicator:
    created: FakeIndicator | None = None

    def __init__(self, indicator_id: str, icon: str, category: str) -> None:
        self.indicator_id = indicator_id
        self.icon = icon
        self.category = category
        self.status = None
        self.menu = None
        FakeIndicator.created = self

    @classmethod
    def new(cls, indicator_id: str, icon: str, category: str) -> FakeIndicator:
        return cls(indicator_id, icon, category)

    def set_status(self, status: str) -> None:
        self.status = status

    def set_menu(self, menu: FakeMenu) -> None:
        self.menu = menu


class FakeIndicatorApi:
    Indicator = FakeIndicator

    class IndicatorCategory:
        APPLICATION_STATUS = "application"

    class IndicatorStatus:
        ACTIVE = "active"


class FakeWindow:
    def __init__(self) -> None:
        self.hidden = False
        self.presented = False

    def hide(self) -> None:
        self.hidden = True

    def deiconify(self) -> None:
        self.presented = True

    def present(self) -> None:
        self.presented = True


def _tray_module():
    assert TRAY.is_file(), "the desktop client has no tray module"
    spec = importlib.util.spec_from_file_location("artek_buddy_tray", TRAY)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_tray_indicator_uses_app_icon_and_open_quit_menu() -> None:
    tray = _tray_module()
    window = FakeWindow()
    quit_calls: list[bool] = []

    indicator = tray.create_tray(
        window,
        lambda: quit_calls.append(True),
        gtk=FakeGtk,
        indicator_api=FakeIndicatorApi,
    )

    assert indicator is FakeIndicator.created
    assert indicator.indicator_id == "artek-buddy"
    assert indicator.icon == "artek-buddy"
    assert indicator.category == "application"
    assert indicator.status == "active"
    assert indicator.menu.shown is True
    assert [item.label for item in indicator.menu.items] == ["Open Artek Buddy", "Quit"]

    indicator.menu.items[0].callback(indicator.menu.items[0])
    assert window.presented is True
    indicator.menu.items[1].callback(indicator.menu.items[1])
    assert quit_calls == [True]


def test_close_hides_only_when_the_tray_is_available() -> None:
    tray = _tray_module()
    window = FakeWindow()

    assert tray.hide_to_tray(window, object()) is True
    assert window.hidden is True

    window.hidden = False
    assert tray.hide_to_tray(window, None) is False
    assert window.hidden is False
