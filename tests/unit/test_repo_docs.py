from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_vision_and_agents_md_exist() -> None:
    vision = ROOT / "VISION.md"
    agents = ROOT / "AGENTS.md"
    assert vision.is_file(), "VISION.md must exist at repo root"
    assert agents.is_file(), "AGENTS.md must exist at repo root"

    vision_text = vision.read_text(encoding="utf-8")
    assert "Kubernetes" in vision_text
    assert "Redis" in vision_text
    assert "Team vs Private" in vision_text

    agents_text = agents.read_text(encoding="utf-8")
    assert "VISION.md" in agents_text
    assert "ARCHITECTURE.md" in agents_text
    assert "THREAT-MODEL.md" in agents_text
    assert "make check" in agents_text
