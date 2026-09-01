from __future__ import annotations

import sys
from pathlib import Path

CLIENT = Path(__file__).resolve().parents[2] / "client"
if str(CLIENT) not in sys.path:
    sys.path.insert(0, str(CLIENT))

from window_chrome import bind_window_active, window_active_script


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
