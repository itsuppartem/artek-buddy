from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ARCHITECTURE = (ROOT / "ARCHITECTURE.md").read_text(encoding="utf-8")
MIGRATIONS = ROOT / "src" / "artek_buddy" / "db" / "migrations"


def test_architecture_migration_count_matches_the_tree() -> None:
    files = list(MIGRATIONS.glob("*.sql"))
    assert files, "migrations directory is empty"
    assert f"{len(files)} SQL files" in ARCHITECTURE


def test_architecture_names_host_callback_and_release_dispatch() -> None:
    assert "CONNECTIONS_CALLBACK_URL" in ARCHITECTURE
    assert "redirect_url" in ARCHITECTURE
    assert "workflow_dispatch" in ARCHITECTURE
