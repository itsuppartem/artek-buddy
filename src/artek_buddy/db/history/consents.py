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


class ConsentsMixin:
    def find_consent_grant(
        self,
        bot_id: str,
        action_class: str,
        scope_key: str,
        device_id: str | None = None,
    ) -> str | None:
        with self._conn() as conn:
            if device_id:
                row = conn.execute(
                    """
                    SELECT id FROM consent_grants
                    WHERE bot_id = %s AND action_class = %s AND scope_key = %s
                      AND (device_id IS NULL OR device_id = %s)
                    LIMIT 1
                    """,
                    (bot_id, action_class, scope_key, device_id),
                ).fetchone()
            else:
                row = conn.execute(
                    """
                    SELECT id FROM consent_grants
                    WHERE bot_id = %s AND action_class = %s AND scope_key = %s
                    LIMIT 1
                    """,
                    (bot_id, action_class, scope_key),
                ).fetchone()
            conn.commit()
        return row["id"] if row else None

    def save_consent_grant(
        self,
        bot_id: str,
        action_class: str,
        scope_key: str,
        device_id: str | None = None,
        workspace_id: str = DEFAULT_WORKSPACE_ID,
    ) -> str:
        grant_id = new_id("cng")
        now = isoformat_utc()
        with self._conn() as conn:
            try:
                conn.execute(
                    """
                    INSERT INTO consent_grants (
                        id, workspace_id, bot_id, device_id, action_class, scope_key, created_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s)
                    """,
                    (grant_id, workspace_id, bot_id, device_id, action_class, scope_key, now),
                )
                conn.commit()
            except UniqueViolation:
                conn.rollback()
        return grant_id

    def create_consent_request(
        self,
        request_id: str,
        *,
        bot_id: str,
        action_class: str,
        scope_key: str,
        summary: str,
        run_id: str | None = None,
        thread_id: str | None = None,
        message_id: str | None = None,
        workspace_id: str = DEFAULT_WORKSPACE_ID,
    ) -> None:
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO consent_requests (
                    id, workspace_id, bot_id, run_id, thread_id, message_id,
                    action_class, scope_key, summary, status, created_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 'pending', %s)
                """,
                (
                    request_id,
                    workspace_id,
                    bot_id,
                    run_id,
                    thread_id,
                    message_id,
                    action_class,
                    scope_key,
                    summary,
                    isoformat_utc(),
                ),
            )
            conn.commit()

    def get_consent_request(self, request_id: str) -> Any:
        from artek_buddy.consent import ConsentRequest

        with self._conn() as conn:
            row = conn.execute(
                """
                SELECT id, bot_id, action_class, scope_key, summary, status, run_id, message_id
                FROM consent_requests WHERE id = %s
                """,
                (request_id,),
            ).fetchone()
            conn.commit()
        if row is None:
            return None
        return ConsentRequest(
            id=row["id"],
            bot_id=row["bot_id"],
            action_class=row["action_class"],
            scope_key=row["scope_key"],
            summary=row["summary"],
            status=row["status"],
            run_id=row["run_id"],
            message_id=row["message_id"],
        )

    def pending_auto_consent_id(self, bot_id: str, run_id: str | None) -> str | None:
        if not run_id:
            return None
        with self._conn() as conn:
            row = conn.execute(
                """
                SELECT id FROM consent_requests
                WHERE bot_id = %s AND run_id = %s AND status = 'pending' AND message_id IS NULL
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (bot_id, run_id),
            ).fetchone()
            conn.commit()
        return str(row["id"]) if row else None

    def answer_consent_request(
        self,
        request_id: str,
        decision: str,
        device_id: str | None,
    ) -> Any:
        from artek_buddy.consent import ConsentRequest

        now = isoformat_utc()
        with self._conn() as conn:
            row = conn.execute(
                """
                UPDATE consent_requests
                SET status = %s, device_id = %s, answered_at = %s
                WHERE id = %s AND status = 'pending'
                RETURNING id, bot_id, action_class, scope_key, summary, status, run_id, message_id
                """,
                (decision, device_id if device_id != "host" else None, now, request_id),
            ).fetchone()
            conn.commit()
        if row is None:
            return None
        return ConsentRequest(
            id=row["id"],
            bot_id=row["bot_id"],
            action_class=row["action_class"],
            scope_key=row["scope_key"],
            summary=row["summary"],
            status=row["status"],
            run_id=row["run_id"],
            message_id=row["message_id"],
        )
