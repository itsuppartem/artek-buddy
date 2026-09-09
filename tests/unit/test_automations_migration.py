from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_automations_migration_exists() -> None:
    path = ROOT / "src" / "artek_buddy" / "db" / "migrations" / "0032_automations.sql"
    assert path.is_file()
    text = path.read_text(encoding="utf-8")
    assert "CREATE TABLE IF NOT EXISTS automations" in text
    assert "idempotency_key TEXT NOT NULL UNIQUE" in text
