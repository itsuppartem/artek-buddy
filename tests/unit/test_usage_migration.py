from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_usage_migration_exists() -> None:
    path = ROOT / "src" / "artek_buddy" / "db" / "migrations" / "0033_usage.sql"
    assert path.is_file()
    text = path.read_text(encoding="utf-8")
    assert "CREATE TABLE IF NOT EXISTS usage_records" in text
    assert "run_id TEXT UNIQUE" in text
    assert "REFERENCES bots (id) ON DELETE CASCADE" in text
