from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_compose_healthchecks_use_readyz() -> None:
    for name in (
        "docker-compose.yml",
        "docker-compose.release.yml",
        "docker-compose.ci.yml",
    ):
        text = (ROOT / name).read_text(encoding="utf-8")
        assert "8080/readyz" in text, name
        assert "8080/health')" not in text, name
