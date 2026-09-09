from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_usage_cost_migration_exists() -> None:
    path = ROOT / "src" / "artek_buddy" / "db" / "migrations" / "0035_usage_cost.sql"
    assert path.is_file()
    text = path.read_text(encoding="utf-8")
    assert "ALTER TABLE usage_records" in text
    assert "cost_usd_micros BIGINT" in text
