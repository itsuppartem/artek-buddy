from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_host_playwright_pin_matches_tests() -> None:
    req = (ROOT / "requirements.txt").read_text(encoding="utf-8")
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert "playwright==1.62.0" in req
    assert "playwright>=" not in req
    assert "playwright==1.62.0" in pyproject
