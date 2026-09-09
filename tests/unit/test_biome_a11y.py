from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_biome_a11y_rules_are_on() -> None:
    data = json.loads((ROOT / "client" / "web" / "biome.json").read_text(encoding="utf-8"))
    assert data["linter"]["rules"].get("a11y") != "off"
    assert data["linter"]["rules"]["recommended"] is True
