from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_run_usage_fast_migration_exists() -> None:
    path = ROOT / "src" / "artek_buddy" / "db" / "migrations" / "0036_run_usage_fast.sql"
    assert path.is_file()
    text = path.read_text(encoding="utf-8")
    assert "CREATE TABLE IF NOT EXISTS run_usage_fast" in text
    assert "fast BOOLEAN NOT NULL" in text
