from __future__ import annotations

from collections.abc import Callable
from typing import Any

from pairing import _log


def _load_tray_modules() -> tuple[Any, Any]:
    import gi

    gi.require_version("Gtk", "3.0")
    from gi.repository import Gtk

    try:
        gi.require_version("AyatanaAppIndicator3", "0.1")
        from gi.repository import AyatanaAppIndicator3 as IndicatorApi
    except (ImportError, ValueError):
        gi.require_version("AppIndicator3", "0.1")
        from gi.repository import AppIndicator3 as IndicatorApi
    return Gtk, IndicatorApi


def _show_window(window: object) -> None:
    for method_name in ("show_all", "deiconify", "present"):
        method = getattr(window, method_name, None)
        if callable(method):
            method()


def create_tray(
    window: object,
    quit_app: Callable[[], None],
    *,
    gtk: Any | None = None,
    indicator_api: Any | None = None,
) -> object | None:
    try:
        if gtk is None or indicator_api is None:
            gtk, indicator_api = _load_tray_modules()
        indicator = indicator_api.Indicator.new(
            "artek-buddy",
            "artek-buddy",
            indicator_api.IndicatorCategory.APPLICATION_STATUS,
        )
        menu = gtk.Menu()
        open_item = gtk.MenuItem(label="Open Artek Buddy")
        open_item.connect("activate", lambda *_args: _show_window(window))
        menu.append(open_item)
        quit_item = gtk.MenuItem(label="Quit")
        quit_item.connect("activate", lambda *_args: quit_app())
        menu.append(quit_item)
        menu.show_all()
        indicator.set_status(indicator_api.IndicatorStatus.ACTIVE)
        indicator.set_menu(menu)
        return indicator
    except Exception as exc:
        _log(f"tray unavailable: {type(exc).__name__}")
        return None


def hide_to_tray(window: object, indicator: object | None) -> bool:
    if indicator is None:
        return False
    connected = getattr(indicator, "get_property", None)
    if callable(connected):
        try:
            if not bool(connected("connected")):
                return False
        except Exception:
            return False
    hide = getattr(window, "hide", None)
    if not callable(hide):
        return False
    hide()
    return True
