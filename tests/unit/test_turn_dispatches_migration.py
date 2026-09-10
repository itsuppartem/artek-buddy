from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_turn_dispatches_migration_exists() -> None:
    path = ROOT / "src" / "artek_buddy" / "db" / "migrations" / "0039_turn_dispatches.sql"
    assert path.is_file()
    text = path.read_text(encoding="utf-8")
    assert "CREATE TABLE IF NOT EXISTS turn_dispatches" in text
    assert "state TEXT NOT NULL" in text
    assert "pending" in text
