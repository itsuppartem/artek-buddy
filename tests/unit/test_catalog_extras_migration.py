from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_catalog_extras_migration_exists() -> None:
    path = ROOT / "src" / "artek_buddy" / "db" / "migrations" / "0034_model_catalog_extras.sql"
    assert path.is_file()
    text = path.read_text(encoding="utf-8")
    assert "ALTER TABLE model_catalog" in text
    assert "extras JSONB NOT NULL" in text
    assert "DEFAULT '{}'::jsonb" in text
