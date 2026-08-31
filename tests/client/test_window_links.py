from __future__ import annotations

import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import patch

CLIENT = Path(__file__).resolve().parents[2] / "client"
if str(CLIENT) not in sys.path:
    sys.path.insert(0, str(CLIENT))

import window


class _View:
    def __init__(self) -> None:
        self.signals: dict[str, object] = {}

    def connect(self, name: str, callback: object) -> None:
        self.signals[name] = callback

    def load_uri(self, _url: str) -> None:
        return None


class _Window:
    def set_default_size(self, _width: int, _height: int) -> None:
        return None

    def connect(self, _name: str, _callback: object) -> None:
        return None

    def add(self, _view: object) -> None:
        return None

    def show_all(self) -> None:
        return None


class _Decision:
    def __init__(self, uri: str) -> None:
        self.uri = uri
        self.ignored = False

    def get_navigation_action(self) -> object:
        request = SimpleNamespace(get_uri=lambda: self.uri)
        return SimpleNamespace(get_request=lambda: request)

    def ignore(self) -> None:
        self.ignored = True


def _webkit_modules(view: _View) -> dict[str, ModuleType]:
    gi = ModuleType("gi")
    gi.require_version = lambda *_args: None  # type: ignore[attr-defined]
    repository = ModuleType("gi.repository")
    repository.Gtk = SimpleNamespace(  # type: ignore[attr-defined]
        Window=lambda **_kwargs: _Window(),
        main=lambda: None,
        main_quit=lambda: None,
    )
    repository.WebKit2 = SimpleNamespace(WebView=lambda: view)  # type: ignore[attr-defined]
    gi.repository = repository  # type: ignore[attr-defined]
    return {"gi": gi, "gi.repository": repository}


def test_external_http_url_accepts_only_external_browser_links() -> None:
    local = "http://127.0.0.1:4173/app"
    assert window.external_http_url("https://example.com/docs", local) == (
        "https://example.com/docs"
    )
    assert window.external_http_url(local, local) is None
    assert window.external_http_url("/relative", local) is None
    assert window.external_http_url("javascript:alert(1)", local) is None
    assert window.external_http_url("https://owner@example.com", local) is None


def test_webkit_window_binds_external_link_policy(monkeypatch) -> None:
    view = _View()
    opened: list[str] = []
    monkeypatch.setattr(window, "apply_window_icon", lambda _window: None)
    monkeypatch.setattr(window, "_register_window", lambda _window: None)
    monkeypatch.setattr(window, "_unregister_window", lambda _window: None)
    monkeypatch.setattr(window.webbrowser, "open", lambda uri, **_kwargs: opened.append(uri))

    with patch.dict(sys.modules, _webkit_modules(view)):
        assert window._open_webkit2("http://127.0.0.1:4173") is True

    assert "decide-policy" in view.signals
    callback = view.signals["decide-policy"]
    assert callable(callback)
    external = _Decision("https://example.com/docs")
    assert callback(view, external, object()) is True
    assert external.ignored is True
    assert opened == ["https://example.com/docs"]

    local = _Decision("http://127.0.0.1:4173/app")
    assert callback(view, local, object()) is False
    assert local.ignored is False
    assert opened == ["https://example.com/docs"]
