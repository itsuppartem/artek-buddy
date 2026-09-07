from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_migration_0031_creates_search_documents() -> None:
    migration_file = (
        ROOT / "src" / "artek_buddy" / "db" / "migrations" / "0031_search_documents.sql"
    )
    assert migration_file.is_file()
    text = migration_file.read_text(encoding="utf-8")
    assert "CREATE TABLE IF NOT EXISTS search_documents" in text
    assert "USING GIN (search_vector)" in text
    assert "to_tsvector('simple'" in text
    assert "deleted_at" in text
