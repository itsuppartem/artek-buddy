from __future__ import annotations

import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PYPROJECT = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
TEST_YML = (ROOT / ".github" / "workflows" / "test.yml").read_text(encoding="utf-8")

# Measured 2026-09-03 on backend (unit+api+client, --cov-branch).
# Floors sit a little under that line except tiny files already at 100%.
REQUIRED_FLOORS = {
    "src/artek_buddy/auth.py": 100,
    "src/artek_buddy/fs_jail.py": 80,
    "src/artek_buddy/db/connection.py": 100,
    "src/artek_buddy/db/sql_split.py": 75,
    "src/artek_buddy/db/history/store.py": 80,
    "src/artek_buddy/supervisor/logic.py": 60,
}


def test_global_coverage_floor_matches_remeasured_total() -> None:
    assert PYPROJECT["tool"]["coverage"]["report"]["fail_under"] == 71
    comment = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert "Measured 2026-09-03" in comment
    assert "--cov-fail-under=71" in TEST_YML


def test_security_module_coverage_floors_are_wired() -> None:
    floors = PYPROJECT["tool"]["artek"]["coverage_floors"]
    for path, floor in REQUIRED_FLOORS.items():
        assert floors[path] == floor
    assert "tests/coverage_floors_gate.py" in TEST_YML
