from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_run_waits_migration_exists() -> None:
    path = ROOT / "src" / "artek_buddy" / "db" / "migrations" / "0037_run_waits.sql"
    assert path.is_file()
    text = path.read_text(encoding="utf-8")
    assert "CREATE TABLE IF NOT EXISTS run_waits" in text
    assert "waiting_recovery" not in text
    assert "continue" in text
    assert "new_attempt" in text
