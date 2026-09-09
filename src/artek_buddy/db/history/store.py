from __future__ import annotations

import hashlib
import logging
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from psycopg import InterfaceError, OperationalError
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool, PoolTimeout

from artek_buddy.db.connection import MIGRATIONS_DIR, DatabaseUnavailable
from artek_buddy.db.shaping import (
    DEFAULT_WORKSPACE_ID,
)
from artek_buddy.db.sql_split import split_sql_statements

log = logging.getLogger("artek_buddy")

# Session lock so host API and worker cannot apply the same file at once.
# Advisory key space is not a secret; 872451 is this product's schema_migrations.
MIGRATION_LOCK_KEY = 872451


class InboxFullError(Exception):
    pass


class MigrationChecksumError(ValueError):
    """A recorded migration file no longer matches the sha256 stored at apply."""


class HistoryStoreCore:
    def __init__(self, database_url: str) -> None:
        self.database_url = database_url
        self._pool: ConnectionPool | None = None

    def open(self) -> None:
        try:
            self._pool = ConnectionPool(
                conninfo=self.database_url,
                min_size=1,
                max_size=8,
                timeout=10,
                kwargs={"row_factory": dict_row, "autocommit": False},
                open=True,
            )
            self.ping()
        except DatabaseUnavailable:
            self.close()
            raise
        except Exception as err:
            self.close()
            raise DatabaseUnavailable(str(err)) from err

    def close(self) -> None:
        pool = self._pool
        self._pool = None
        if pool is not None:
            try:
                pool.close()
            except Exception:
                log.exception("error closing postgres pool")

    def ping(self) -> bool:
        with self._conn() as conn:
            conn.execute("SELECT 1")
            conn.commit()
        return True

    def available(self) -> bool:
        if self._pool is None:
            return False
        try:
            return self.ping()
        except DatabaseUnavailable:
            return False

    @contextmanager
    def _conn(self) -> Iterator[Any]:
        if self._pool is None:
            raise DatabaseUnavailable()
        try:
            with self._pool.connection() as conn:
                yield conn
        except DatabaseUnavailable:
            raise
        except (OperationalError, InterfaceError, OSError, PoolTimeout) as err:
            raise DatabaseUnavailable(str(err)) from err

    def apply_migrations(self) -> None:
        files = sorted(MIGRATIONS_DIR.glob("*.sql"))
        with self._conn() as conn:
            conn.execute("SELECT pg_advisory_lock(%s)", (MIGRATION_LOCK_KEY,)).fetchone()
            try:
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS schema_migrations (
                        id TEXT PRIMARY KEY,
                        applied_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                        checksum TEXT NOT NULL DEFAULT ''
                    )
                    """
                )
                conn.execute(
                    "ALTER TABLE schema_migrations "
                    "ADD COLUMN IF NOT EXISTS checksum TEXT NOT NULL DEFAULT ''"
                )
                conn.commit()
                recorded = {
                    row["id"]: row["checksum"] or ""
                    for row in conn.execute("SELECT id, checksum FROM schema_migrations").fetchall()
                }
                for path in files:
                    digest = hashlib.sha256(path.read_bytes()).hexdigest()
                    if path.name in recorded:
                        previous = recorded[path.name]
                        if previous and previous != digest:
                            raise MigrationChecksumError(
                                f"migration {path.name} checksum mismatch: "
                                f"recorded {previous}, file {digest}"
                            )
                        if not previous:
                            conn.execute(
                                "UPDATE schema_migrations SET checksum = %s WHERE id = %s",
                                (digest, path.name),
                            )
                            conn.commit()
                        continue
                    sql = path.read_text(encoding="utf-8")
                    for statement in split_sql_statements(sql):
                        conn.execute(statement)
                    conn.execute(
                        "INSERT INTO schema_migrations (id, checksum) VALUES (%s, %s)",
                        (path.name, digest),
                    )
                    conn.commit()
                    log.info("applied migration %s", path.name)
            finally:
                try:
                    conn.rollback()
                except Exception:
                    pass
                conn.execute("SELECT pg_advisory_unlock(%s)", (MIGRATION_LOCK_KEY,)).fetchone()
                conn.commit()

    def ensure_workspace(self) -> None:
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO workspaces (id) VALUES (%s) ON CONFLICT (id) DO NOTHING",
                (DEFAULT_WORKSPACE_ID,),
            )
            conn.commit()
