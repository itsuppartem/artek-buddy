from __future__ import annotations

from pathlib import Path


class DatabaseUnavailable(Exception):
    """Postgres cannot be reached. HTTP layer maps this to 503 retryable."""

    retryable = True

    def __init__(self, message: str = "postgres is unavailable") -> None:
        super().__init__(message)


MIGRATIONS_DIR = Path(__file__).resolve().parent / "migrations"
