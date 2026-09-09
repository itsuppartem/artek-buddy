from __future__ import annotations

import sys
from pathlib import Path

CLIENT = Path(__file__).resolve().parents[2] / "client"
if str(CLIENT) not in sys.path:
    sys.path.insert(0, str(CLIENT))

from window_chrome import (
    _gtk_window_looking,
    _register_window,
    _unregister_window,
    bind_window_active,
    gtk_window_active,
    remember_window_active,
    window_active_script,
)

# Gdk.WindowState in GTK3 (gdkwindow.h): WITHDRAWN = 1<<0, ICONIFIED = 1<<1.
_ICONIFIED = 1 << 1
_WITHDRAWN = 1 << 0


def test_window_active_script_calls_the_page_hook() -> None:
    assert "__artekSetWindowActive(false)" in window_active_script(False)
    assert "__artekSetWindowActive(true)" in window_active_script(True)


def test_bind_window_active_pushes_gtk_is_active_into_the_page() -> None:
    scripts: list[str] = []

    class View:
        def __init__(self) -> None:
            self.signals: dict[str, object] = {}

        def connect(self, name: str, callback: object) -> None:
            self.signals[name] = callback

        def run_javascript(self, script: str, *_args: object) -> None:
            scripts.append(script)

    class Window:
        def __init__(self) -> None:
            self.signals: dict[str, object] = {}
            self.active = True

        def connect(self, name: str, callback: object) -> None:
            self.signals[name] = callback

        def is_active(self) -> bool:
            return self.active

    view = View()
    window = Window()
    bind_window_active(view, window)
    assert "notify::is-active" in window.signals
    window.active = False
    on_active = window.signals["notify::is-active"]
    assert callable(on_active)
    on_active(window)
    assert any("__artekSetWindowActive(false)" in item for item in scripts)
    load = view.signals.get("load-changed") or view.signals.get("load-finished")
    assert callable(load)
    window.active = True
    scripts.clear()
    load(view, object())
    assert any("__artekSetWindowActive(true)" in item for item in scripts)


class _View:
    def __init__(self) -> None:
        self.signals: dict[str, object] = {}
        self.scripts: list[str] = []

    def connect(self, name: str, callback: object) -> None:
        self.signals[name] = callback

    def run_javascript(self, script: str, *_args: object) -> None:
        self.scripts.append(script)


class _GdkWindow:
    def __init__(self, state: int = 0) -> None:
        self.state = state

    def get_state(self) -> int:
        return self.state


class _WindowStateEvent:
    def __init__(self, new_window_state: int) -> None:
        self.new_window_state = new_window_state


class _Window:
    def __init__(self, *, active: bool = True, state: int = 0) -> None:
        self.signals: dict[str, object] = {}
        self.active = active
        self.gdk = _GdkWindow(state)

    def connect(self, name: str, callback: object) -> None:
        self.signals[name] = callback

    def is_active(self) -> bool:
        return self.active

    def get_window(self) -> _GdkWindow:
        return self.gdk


def test_gtk_window_looking_is_false_when_iconified_even_if_is_active_stays_true() -> None:
    window = _Window(active=True, state=_ICONIFIED)
    assert _gtk_window_looking(window) is False
    window.gdk.state = 0
    assert _gtk_window_looking(window) is True


def test_gtk_window_looking_is_false_when_withdrawn() -> None:
    window = _Window(active=True, state=_WITHDRAWN)
    assert _gtk_window_looking(window) is False


def test_bind_window_active_treats_iconify_as_inactive_even_when_is_active_stays_true() -> None:
    view = _View()
    window = _Window(active=True, state=0)
    _register_window(window)
    try:
        bind_window_active(view, window)
        assert "window-state-event" in window.signals
        on_state = window.signals["window-state-event"]
        assert callable(on_state)
        window.gdk.state = _ICONIFIED
        on_state(window, _WindowStateEvent(_ICONIFIED))
        assert gtk_window_active() is False
        assert any("__artekSetWindowActive(false)" in item for item in view.scripts)

        view.scripts.clear()
        on_active = window.signals["notify::is-active"]
        assert callable(on_active)
        on_active(window, object())
        assert gtk_window_active() is False
        assert any("__artekSetWindowActive(false)" in item for item in view.scripts)

        view.scripts.clear()
        window.gdk.state = 0
        on_state(window, _WindowStateEvent(0))
        assert gtk_window_active() is True
        assert any("__artekSetWindowActive(true)" in item for item in view.scripts)
    finally:
        _unregister_window(window)


def test_bind_window_active_treats_withdrawn_as_inactive() -> None:
    view = _View()
    window = _Window(active=True, state=0)
    _register_window(window)
    try:
        bind_window_active(view, window)
        on_state = window.signals["window-state-event"]
        assert callable(on_state)
        window.gdk.state = _WITHDRAWN
        on_state(window, _WindowStateEvent(_WITHDRAWN))
        assert gtk_window_active() is False
        assert any("__artekSetWindowActive(false)" in item for item in view.scripts)
    finally:
        _unregister_window(window)


def test_gtk_window_active_is_a_cache_not_a_cross_thread_widget_read() -> None:
    window = object()
    _register_window(window)
    try:
        remember_window_active(False)
        assert gtk_window_active() is False
        remember_window_active(True)
        assert gtk_window_active() is True
    finally:
        _unregister_window(window)
    assert gtk_window_active() is None
