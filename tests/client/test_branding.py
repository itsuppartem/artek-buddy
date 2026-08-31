from __future__ import annotations

import sys
from pathlib import Path

CLIENT_DIR = Path(__file__).resolve().parents[2] / "client"
ASSETS = CLIENT_DIR / "assets"
BUILD_DEB = CLIENT_DIR / "build-deb.sh"


def test_mascot_pngs_exist() -> None:
    files = [
        ASSETS / "app-icon.png",
        ASSETS / "web" / "bot-mark.png",
        ASSETS / "web" / "pairing-mark.png",
        ASSETS / "web" / "favicon.png",
        ASSETS / "hicolor" / "256x256" / "apps" / "artek-buddy.png",
        ASSETS / "hicolor" / "48x48" / "apps" / "artek-buddy.png",
    ]
    for path in files:
        data = path.read_bytes()
        assert data[:8] == b"\x89PNG\r\n\x1a\n", path


def test_deb_script_installs_artek_icon() -> None:
    text = BUILD_DEB.read_text(encoding="utf-8")
    assert "Icon=artek-buddy" in text
    assert "utilities-terminal" not in text
    assert "icons/hicolor" in text
    assert "client/assets/app-icon.png" in text
    assert "owner_paths.py" in text
    assert "window_chrome.py" in text
    assert "pairing.py" in text
    assert "proxy.py" in text
    assert "notifications.py" in text
    assert "window.py" in text
    assert "clipboard_image.py" in text
    assert "web_paths.py" in text


def test_bundled_icon_path_finds_source_tree(client_mod) -> None:
    icon = client_mod.bundled_icon_path()
    assert icon is not None
    assert icon.is_file()
    assert icon.name in {"app-icon.png", "artek-buddy.png"}


def test_notify_passes_bundled_icon(client_mod, monkeypatch) -> None:
    seen: dict[str, list[str]] = {}

    def fake_run(cmd, **_kwargs):
        seen["cmd"] = list(cmd)
        return None

    notify_mod = sys.modules["notifications"]
    monkeypatch.delenv("ARTEK_BUDDY_NOTIFY", raising=False)
    monkeypatch.setattr(notify_mod.shutil, "which", lambda _name: "/usr/bin/notify-send")
    monkeypatch.setattr(notify_mod.subprocess, "run", fake_run)
    monkeypatch.setattr(notify_mod, "_apply_urgency", lambda *_args: None)
    client_mod._desktop_notify("Hello", "Body", "normal")
    cmd = seen["cmd"]
    icon_args = [item for item in cmd if str(item).startswith("--icon=")]
    assert icon_args
    assert icon_args[0].endswith(".png")
