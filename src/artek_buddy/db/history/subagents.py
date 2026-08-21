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


class SubagentsMixin:
    def create_subagent(
        self,
        bot: Bot,
        name: str,
        task: str,
        parent_run_id: str | None = None,
    ) -> Subagent:
        with self._conn() as conn:
            with conn.transaction():
                row = conn.execute(
                    "SELECT COALESCE(MAX(seq), 0) AS n FROM subagents WHERE bot_id = %s",
                    (bot.id,),
                ).fetchone()
                seq = int(row["n"] if row else 0) + 1
                now = isoformat_utc()
                sub_id = new_id("sub")
                conn.execute(
                    """
                    INSERT INTO subagents (
                        id, bot_id, thread_id, parent_run_id, cursor_agent_id,
                        seq, name, task, status, created_at, updated_at
                    ) VALUES (
                        %s, %s, %s, %s, NULL,
                        %s, %s, %s, 'queued', %s, %s
                    )
                    """,
                    (
                        sub_id,
                        bot.id,
                        bot.thread_id,
                        parent_run_id,
                        seq,
                        name.strip() or f"task {seq}",
                        task,
                        now,
                        now,
                    ),
                )
        found = self.get_subagent(sub_id)
        if found is None:
            raise RuntimeError("failed to persist subagent")
        return found

    def get_subagent(self, subagent_id: str) -> Subagent | None:
        with self._conn() as conn:
            row = conn.execute("SELECT * FROM subagents WHERE id = %s", (subagent_id,)).fetchone()
            conn.commit()
        return self._subagent_from_row(row) if row else None

    def list_subagents(self, bot_id: str, limit: int = 40) -> list[Subagent]:
        with self._conn() as conn:
            rows = conn.execute(
                """
                SELECT * FROM subagents
                WHERE bot_id = %s
                ORDER BY seq DESC
                LIMIT %s
                """,
                (bot_id, max(1, min(limit, 100))),
            ).fetchall()
            conn.commit()
        return [self._subagent_from_row(row) for row in rows]

    def resolve_subagent(self, bot_id: str, ref: str) -> Subagent | None:
        text = (ref or "").strip()
        if not text:
            return None
        if text.startswith("sub_"):
            found = self.get_subagent(text)
            if found and found.bot_id == bot_id:
                return found
            return None
        if text.isdigit():
            with self._conn() as conn:
                row = conn.execute(
                    "SELECT * FROM subagents WHERE bot_id = %s AND seq = %s",
                    (bot_id, int(text)),
                ).fetchone()
                conn.commit()
            return self._subagent_from_row(row) if row else None
        with self._conn() as conn:
            row = conn.execute(
                """
                SELECT * FROM subagents
                WHERE bot_id = %s AND lower(name) = lower(%s)
                ORDER BY seq DESC
                LIMIT 1
                """,
                (bot_id, text),
            ).fetchone()
            conn.commit()
        return self._subagent_from_row(row) if row else None

    def running_subagent_count(self, bot_id: str) -> int:
        with self._conn() as conn:
            row = conn.execute(
                """
                SELECT COUNT(*) AS n FROM subagents
                WHERE bot_id = %s AND status IN ('queued', 'running')
                """,
                (bot_id,),
            ).fetchone()
            conn.commit()
        return int(row["n"]) if row else 0

    def update_subagent(
        self,
        subagent_id: str,
        *,
        status: str | None = None,
        cursor_agent_id: str | None = None,
        progress: str | None = None,
        thinking: str | None = None,
        result: str | None = None,
        error: str | None = None,
        clarifications: str | None = None,
        clear_output: bool = False,
    ) -> Subagent | None:
        assignments = ["updated_at = %s"]
        values: list[Any] = [isoformat_utc()]
        if status is not None:
            assignments.append("status = %s")
            values.append(status)
        if cursor_agent_id is not None:
            assignments.append("cursor_agent_id = %s")
            values.append(cursor_agent_id)
        if progress is not None:
            assignments.append("progress = %s")
            values.append(progress)
        if thinking is not None:
            assignments.append("thinking = %s")
            values.append(thinking)
        if result is not None:
            assignments.append("result = %s")
            values.append(result)
        if error is not None:
            assignments.append("error = %s")
            values.append(error)
        if clarifications is not None:
            assignments.append("clarifications = %s")
            values.append(clarifications)
        if clear_output:
            assignments.append("progress = NULL")
            assignments.append("thinking = NULL")
            assignments.append("result = NULL")
            assignments.append("error = NULL")
        values.append(subagent_id)
        with self._conn() as conn:
            row = conn.execute(
                f"UPDATE subagents SET {', '.join(assignments)} WHERE id = %s RETURNING *",
                values,
            ).fetchone()
            conn.commit()
        return self._subagent_from_row(row) if row else None

    def _subagent_from_row(self, row: dict[str, Any]) -> Subagent:
        return Subagent(
            id=row["id"],
            bot_id=row["bot_id"],
            thread_id=row["thread_id"],
            parent_run_id=row["parent_run_id"],
            cursor_agent_id=row.get("cursor_agent_id"),
            index=int(row["seq"]),
            name=row["name"],
            task=row["task"],
            status=row["status"],
            progress=row.get("progress"),
            thinking=row.get("thinking"),
            result=row.get("result"),
            error=row.get("error"),
            clarifications=row.get("clarifications"),
            created_at=parse_iso(row["created_at"]),
            updated_at=parse_iso(row["updated_at"]),
        )

    def append_clarification(self, subagent_id: str, text: str) -> Subagent | None:
        note = (text or "").strip()
        if not note:
            return self.get_subagent(subagent_id)
        found = self.get_subagent(subagent_id)
        if found is None:
            return None
        previous = (found.clarifications or "").strip()
        merged = f"{previous}\n{note}".strip() if previous else note
        return self.update_subagent(subagent_id, clarifications=merged)
