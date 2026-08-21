from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_startup_keepalive_does_not_spawn_xterm() -> None:
    text = (ROOT / "infra" / "computer" / "start.sh").read_text(encoding="utf-8")
    keepalive = text.split("while kill -0", 1)[1]
    assert "xterm" not in keepalive
    assert text.count("xterm ") == 1
    assert "/tmp/artek/xterm.fallback" in text
