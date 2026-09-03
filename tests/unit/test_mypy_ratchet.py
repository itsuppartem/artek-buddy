from __future__ import annotations

import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PYPROJECT = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))

RATCHET_MODULES = {
    "artek_buddy.auth",
    "artek_buddy.fs_jail",
    "artek_buddy.db.connection",
    "artek_buddy.db.sql_split",
    "artek_buddy.db.history.store",
}
RATCHET_CODES = {
    "attr-defined",
    "arg-type",
    "union-attr",
    "assignment",
}


def test_mypy_keeps_a_named_global_baseline() -> None:
    mypy = PYPROJECT["tool"]["mypy"]
    assert set(mypy["disable_error_code"]) >= RATCHET_CODES
    comment = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert "Baseline 2026-09-03" in comment
    assert "295" in comment
    assert "205" not in comment.split("[tool.mypy]", 1)[1].split("[tool.pytest", 1)[0]


def test_mypy_re_enables_codes_on_auth_jail_and_migrations() -> None:
    found: set[str] = set()
    for override in PYPROJECT["tool"]["mypy"].get("overrides") or []:
        enabled = set(override.get("enable_error_code") or [])
        if not RATCHET_CODES <= enabled:
            continue
        raw = override.get("module")
        names = {raw} if isinstance(raw, str) else set(raw or [])
        found |= names
    assert RATCHET_MODULES <= found
