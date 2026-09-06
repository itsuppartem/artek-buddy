from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_migration_0027_file_exists_and_binds_devices() -> None:
    migration_file = ROOT / "src" / "artek_buddy" / "db" / "migrations" / "0027_members.sql"
    assert migration_file.is_file(), "0027_members.sql must exist in migrations directory"

    content = migration_file.read_text(encoding="utf-8")
    assert "CREATE TABLE IF NOT EXISTS members" in content
    assert "INSERT INTO members" in content
    assert "mem_owner" in content
    assert "ALTER TABLE devices ADD COLUMN IF NOT EXISTS member_id" in content
    assert "UPDATE devices SET member_id = 'mem_owner' WHERE member_id IS NULL" in content
