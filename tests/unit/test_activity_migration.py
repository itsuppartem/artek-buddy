from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_migration_0030_file_exists_and_creates_activity() -> None:
    migration_file = ROOT / "src" / "artek_buddy" / "db" / "migrations" / "0030_activity.sql"
    assert migration_file.is_file()
    text = migration_file.read_text(encoding="utf-8")
    assert "CREATE TABLE IF NOT EXISTS activity" in text
    assert "GENERATED ALWAYS AS IDENTITY" in text
    assert "activity_resource_seq_idx" in text
