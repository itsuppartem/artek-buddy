from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_owner_commands_migration_exists() -> None:
    path = ROOT / "src" / "artek_buddy" / "db" / "migrations" / "0038_owner_commands.sql"
    assert path.is_file()
    text = path.read_text(encoding="utf-8")
    assert "CREATE TABLE IF NOT EXISTS owner_commands" in text
    assert "payload_hash" in text
    assert "parent_command_id" in text
