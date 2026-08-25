from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_startup_keepalive_does_not_spawn_xterm() -> None:
    text = (ROOT / "infra" / "computer" / "start.sh").read_text(encoding="utf-8")
    keepalive = text.split("while kill -0", 1)[1]
    assert "xterm" not in keepalive
    assert text.count("xterm ") == 1
    assert "/tmp/artek/xterm.fallback" in text


def test_start_disables_pcmanfm_volume_autorun() -> None:
    text = (ROOT / "infra" / "computer" / "start.sh").read_text(encoding="utf-8")
    assert "autorun=0" in text
    assert "mount_on_startup=0" in text


def test_fluxbox_starts_from_usr_not_a_tmp_script() -> None:
    """Docker tmpfs /tmp is noexec even when the create spec omits that flag."""
    text = (ROOT / "infra" / "computer" / "start.sh").read_text(encoding="utf-8")
    assert "fluxbox -rc /tmp/fluxbox-home/.fluxbox/init" in text
    assert "chmod +x /tmp/fluxbox-home/.fluxbox/startup" not in text
    assert "/tmp/fluxbox-home/.fluxbox/startup" not in text
