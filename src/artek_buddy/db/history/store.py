from __future__ import annotations

import logging
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from typing import Any, Iterator

from psycopg import InterfaceError, OperationalError
from psycopg.errors import UniqueViolation
from psycopg.rows import dict_row
from psycopg.types.json import Json
from psycopg_pool import ConnectionPool, PoolTimeout

from artek_buddy.auth import (
    PAIRING_TTL_SECONDS,
    hash_secret,
    new_device_token,
    new_pairing_code,
    normalize_pairing_code,
)
from artek_buddy.contracts.domain import (
    Artifact,
    Bot,
    Device,
    DeviceCreated,
    MemoryDocument,
    PairingCode,
    Routine,
    Run,
    Subagent,
    ThreadMessage,
    ThreadMessagePage,
)
from artek_buddy.contracts.ids import DEFAULT_BOT_COLOR, MemoryScope, RunStatus
from artek_buddy.cron import CronError, next_run_at, parse_cron, validate_timezone
from artek_buddy.contracts.events import MessageReplyRef, MessageRole
from artek_buddy.db.connection import MIGRATIONS_DIR, DatabaseUnavailable
from artek_buddy.memory import (
    MAX_MEMORY_CONTENT_CHARS,
    MemoryConflict,
    MemoryPathError,
    normalize_memory_path,
)
from artek_buddy.memory_hub import MemoryEntry, entry_path, normalize_kind, shelf_from_path
from artek_buddy.computer.models import ComputerRecord
from artek_buddy.db.shaping import (
    DEFAULT_PAGE_SIZE,
    DEFAULT_WORKSPACE_ID,
    answer_ask_blocks,
    isoformat_utc,
    new_id,
    next_seq,
    older_cursor,
    parse_iso,
    pick_color,
    preview_snippet,
    text_blocks,
    blocks_text,
)

log = logging.getLogger("artek_buddy")


class InboxFullError(Exception):
    pass


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
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    id TEXT PRIMARY KEY,
                    applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
                )
                """
            )
            conn.commit()
            applied = {
                row["id"]
                for row in conn.execute("SELECT id FROM schema_migrations").fetchall()
            }
            for path in files:
                if path.name in applied:
                    continue
                sql = path.read_text(encoding="utf-8")
                for statement in sql.split(";"):
                    statement = statement.strip()
                    if statement:
                        conn.execute(statement)
                conn.execute(
                    "INSERT INTO schema_migrations (id) VALUES (%s)",
                    (path.name,),
                )
                conn.commit()
                log.info("applied migration %s", path.name)

    def ensure_workspace(self) -> None:
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO workspaces (id) VALUES (%s) ON CONFLICT (id) DO NOTHING",
                (DEFAULT_WORKSPACE_ID,),
            )
            conn.commit()
