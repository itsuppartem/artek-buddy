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


class MemoryMixin:
    def create_memory(
        self,
        scope: MemoryScope | str,
        content: str,
        bot_id: str | None = None,
        path: str | None = None,
        workspace_id: str = DEFAULT_WORKSPACE_ID,
        source_run_id: str | None = None,
        source_thread_id: str | None = None,
    ) -> MemoryDocument:
        scope_value = scope.value if isinstance(scope, MemoryScope) else str(scope)
        if scope_value not in {"bot", "user"}:
            raise MemoryPathError("memory scope must be bot or user")
        if scope_value == "bot":
            if not bot_id:
                raise MemoryPathError("bot memory needs a bot")
        else:
            bot_id = None
        if len(content) > MAX_MEMORY_CONTENT_CHARS:
            raise MemoryPathError("memory content is too long")
        path_value = normalize_memory_path(path)
        now = isoformat_utc()
        document_id = new_id("mem")
        with self._conn() as conn:
            try:
                with conn.transaction():
                    conn.execute(
                        "INSERT INTO workspaces (id) VALUES (%s) ON CONFLICT (id) DO NOTHING",
                        (workspace_id,),
                    )
                    conn.execute(
                        """
                        INSERT INTO memory_documents (
                            id, workspace_id, bot_id, scope, path, content,
                            revision, created_at, updated_at
                        ) VALUES (%s, %s, %s, %s, %s, %s, 1, %s, %s)
                        """,
                        (
                            document_id,
                            workspace_id,
                            bot_id,
                            scope_value,
                            path_value,
                            content,
                            now,
                            now,
                        ),
                    )
                    conn.execute(
                        """
                        INSERT INTO memory_revisions (
                            id, document_id, revision, content, source_run_id,
                            source_thread_id, created_at
                        ) VALUES (%s, %s, 1, %s, %s, %s, %s)
                        """,
                        (new_id("mrev"), document_id, content, source_run_id, source_thread_id, now),
                    )
            except UniqueViolation as err:
                raise MemoryConflict("memory document already exists") from err
        return MemoryDocument(
            id=document_id,
            scope=scope_value,
            bot_id=bot_id,
            path=path_value,
            content=content,
            revision=1,
            updated_at=now,
        )

    def list_memory(
        self,
        bot_id: str | None = None,
        scope: MemoryScope | str | None = None,
    ) -> list[MemoryDocument]:
        scope_value = (
            scope.value if isinstance(scope, MemoryScope) else (str(scope) if scope else None)
        )
        clauses = ["TRUE"]
        args: list[Any] = []
        if scope_value == "user":
            clauses.append("scope = 'user'")
        elif scope_value == "bot" and bot_id:
            clauses.append("scope = 'bot' AND bot_id = %s")
            args.append(bot_id)
        elif bot_id:
            clauses.append("((scope = 'bot' AND bot_id = %s) OR scope = 'user')")
            args.append(bot_id)
        with self._conn() as conn:
            rows = conn.execute(
                f"""
                SELECT id, scope, bot_id, path, content, revision, updated_at
                FROM memory_documents
                WHERE {' AND '.join(clauses)}
                ORDER BY updated_at DESC, path ASC
                """,
                args,
            ).fetchall()
            conn.commit()
        return [self._memory_from_row(row) for row in rows]

    def memory_for_agent(self, bot_id: str) -> list[MemoryDocument]:
        return self.list_memory(bot_id=bot_id)

    def get_memory(self, document_id: str) -> MemoryDocument | None:
        with self._conn() as conn:
            row = conn.execute(
                """
                SELECT id, scope, bot_id, path, content, revision, updated_at
                FROM memory_documents WHERE id = %s
                """,
                (document_id,),
            ).fetchone()
            conn.commit()
        return self._memory_from_row(row) if row else None

    def get_memory_by_path(
        self,
        scope: str,
        path: str,
        bot_id: str | None = None,
        workspace_id: str = DEFAULT_WORKSPACE_ID,
    ) -> MemoryDocument | None:
        path_value = normalize_memory_path(path)
        with self._conn() as conn:
            if bot_id:
                row = conn.execute(
                    """
                    SELECT id, scope, bot_id, path, content, revision, updated_at
                    FROM memory_documents
                    WHERE workspace_id = %s AND scope = %s AND bot_id = %s AND path = %s
                    """,
                    (workspace_id, scope, bot_id, path_value),
                ).fetchone()
            else:
                row = conn.execute(
                    """
                    SELECT id, scope, bot_id, path, content, revision, updated_at
                    FROM memory_documents
                    WHERE workspace_id = %s AND scope = %s AND bot_id IS NULL AND path = %s
                    """,
                    (workspace_id, scope, path_value),
                ).fetchone()
            conn.commit()
        return self._memory_from_row(row) if row else None

    def save_memory(
        self,
        scope: MemoryScope | str,
        path: str,
        content: str,
        bot_id: str | None = None,
        workspace_id: str = DEFAULT_WORKSPACE_ID,
        source_run_id: str | None = None,
        source_thread_id: str | None = None,
    ) -> MemoryDocument:
        scope_value = scope.value if isinstance(scope, MemoryScope) else str(scope)
        normalized_path = normalize_memory_path(path)
        existing = self.get_memory_by_path(
            scope_value,
            normalized_path,
            bot_id=bot_id,
            workspace_id=workspace_id,
        )
        if existing is not None:
            updated = self.update_memory(
                existing.id,
                content,
                source_run_id=source_run_id,
                source_thread_id=source_thread_id,
            )
            if updated is not None:
                return updated
        return self.create_memory(
            scope=scope_value,
            content=content,
            bot_id=bot_id,
            path=normalized_path,
            workspace_id=workspace_id,
            source_run_id=source_run_id,
            source_thread_id=source_thread_id,
        )

    def update_memory(
        self,
        document_id: str,
        content: str,
        source_run_id: str | None = None,
        source_thread_id: str | None = None,
    ) -> MemoryDocument | None:
        if len(content) > MAX_MEMORY_CONTENT_CHARS:
            raise MemoryPathError("memory content is too long")
        current = self.get_memory(document_id)
        if current is None:
            return None
        revision = current.revision + 1
        now = isoformat_utc()
        with self._conn() as conn:
            with conn.transaction():
                row = conn.execute(
                    """
                    UPDATE memory_documents
                    SET content = %s, revision = %s, updated_at = %s
                    WHERE id = %s
                    RETURNING id, scope, bot_id, path, content, revision, updated_at
                    """,
                    (content, revision, now, document_id),
                ).fetchone()
                conn.execute(
                    """
                    INSERT INTO memory_revisions (
                        id, document_id, revision, content, source_run_id,
                        source_thread_id, created_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        new_id("mrev"),
                        document_id,
                        revision,
                        content,
                        source_run_id,
                        source_thread_id,
                        now,
                    ),
                )
        document = self._memory_from_row(row) if row else None
        if document is not None:
            linked = self.find_entry_by_document(document.id)
            if linked is not None:
                self.update_entry_text(linked.id, document.content)
        return document

    def delete_memory(self, document_id: str) -> bool:
        with self._conn() as conn:
            conn.execute(
                """
                UPDATE memory_entries
                SET superseded_at = %s
                WHERE document_id = %s AND superseded_at IS NULL
                """,
                (isoformat_utc(), document_id),
            )
            row = conn.execute(
                "DELETE FROM memory_documents WHERE id = %s RETURNING id",
                (document_id,),
            ).fetchone()
            conn.commit()
        return row is not None

    def create_memory_entry(
        self,
        text: str,
        kind: str = "preference",
        scope: str = "user",
        bot_id: str | None = None,
        source: str = "remember",
        source_run_id: str | None = None,
        source_thread_id: str | None = None,
        workspace_id: str = DEFAULT_WORKSPACE_ID,
        slot: str | None = None,
        shelf: str = "owner",
        until: str | None = None,
    ) -> MemoryEntry:
        kind_value = normalize_kind(kind)
        scope_value = "bot" if scope == "bot" and bot_id else "user"
        writer_id = bot_id
        entry_id = new_id("ment")
        layer = shelf if shelf in {"owner", "work", "charter"} else "owner"
        document = self.create_memory(
            scope=scope_value,
            content=text,
            bot_id=writer_id if scope_value == "bot" else None,
            path=entry_path(entry_id, kind_value, layer),
            workspace_id=workspace_id,
            source_run_id=source_run_id,
            source_thread_id=source_thread_id,
        )
        now = isoformat_utc()
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO memory_entries (
                    id, workspace_id, bot_id, scope, kind, slot, text, source,
                    source_run_id, source_thread_id, document_id, created_at,
                    shelf, until
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    entry_id,
                    workspace_id,
                    writer_id,
                    scope_value,
                    kind_value,
                    slot,
                    text,
                    source,
                    source_run_id,
                    source_thread_id,
                    document.id,
                    now,
                    layer,
                    until,
                ),
            )
            conn.commit()
        return MemoryEntry(
            id=entry_id,
            scope=scope_value,
            kind=kind_value,
            text=text,
            source=source,
            bot_id=writer_id,
            document_id=document.id,
            slot=slot,
            shelf=layer,
            until=until,
        )

    def attach_memory_entry(
        self,
        document: MemoryDocument,
        kind: str = "preference",
        source: str = "panel",
        workspace_id: str = DEFAULT_WORKSPACE_ID,
        slot: str | None = None,
        shelf: str | None = None,
        until: str | None = None,
    ) -> MemoryEntry:
        existing = self.find_entry_by_document(document.id)
        if existing is not None:
            return self.update_entry_text(existing.id, document.content) or existing
        kind_value = normalize_kind(kind)
        scope_value = document.scope.value if hasattr(document.scope, "value") else str(document.scope)
        layer = shelf or shelf_from_path(getattr(document, "path", "") or "", scope_value)
        entry_id = new_id("ment")
        now = isoformat_utc()
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO memory_entries (
                    id, workspace_id, bot_id, scope, kind, slot, text, source,
                    document_id, created_at, shelf, until
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    entry_id,
                    workspace_id,
                    document.bot_id,
                    scope_value,
                    kind_value,
                    slot,
                    document.content,
                    source,
                    document.id,
                    now,
                    layer,
                    until,
                ),
            )
            conn.commit()
        return MemoryEntry(
            id=entry_id,
            scope=scope_value,
            kind=kind_value,
            text=document.content,
            source=source,
            bot_id=document.bot_id,
            document_id=document.id,
            slot=slot,
            shelf=layer,
            until=until,
        )

    def list_live_memory_entries(
        self,
        bot_id: str | None = None,
        workspace_id: str = DEFAULT_WORKSPACE_ID,
    ) -> list[MemoryEntry]:
        clauses = [
            "workspace_id = %s",
            "superseded_at IS NULL",
            "(until IS NULL OR until > NOW())",
        ]
        args: list[Any] = [workspace_id]
        if bot_id:
            clauses.append("(scope = 'user' OR bot_id = %s)")
            args.append(bot_id)
        else:
            clauses.append("scope = 'user'")
        with self._conn() as conn:
            rows = conn.execute(
                f"""
                SELECT id, scope, kind, slot, text, source, bot_id, document_id, shelf, until
                FROM memory_entries
                WHERE {' AND '.join(clauses)}
                ORDER BY created_at DESC
                """,
                args,
            ).fetchall()
            conn.commit()
        return [self._entry_from_row(row) for row in rows]

    def find_live_memory_entry_by_slot(
        self,
        slot: str,
        scope: str = "user",
        bot_id: str | None = None,
        workspace_id: str = DEFAULT_WORKSPACE_ID,
    ) -> MemoryEntry | None:
        if not slot:
            return None
        clauses = [
            "workspace_id = %s",
            "superseded_at IS NULL",
            "slot = %s",
            "scope = %s",
        ]
        args: list[Any] = [workspace_id, slot, scope]
        if scope == "bot":
            if not bot_id:
                return None
            clauses.append("bot_id = %s")
            args.append(bot_id)
        with self._conn() as conn:
            row = conn.execute(
                f"""
                SELECT id, scope, kind, slot, text, source, bot_id, document_id, shelf, until
                FROM memory_entries
                WHERE {' AND '.join(clauses)}
                ORDER BY created_at DESC
                LIMIT 1
                """,
                args,
            ).fetchone()
            conn.commit()
        return self._entry_from_row(row) if row else None

    def find_live_memory_entry(
        self,
        text: str,
        scope: str = "user",
        bot_id: str | None = None,
        workspace_id: str = DEFAULT_WORKSPACE_ID,
    ) -> MemoryEntry | None:
        body = (text or "").strip()
        if not body:
            return None
        clauses = [
            "workspace_id = %s",
            "superseded_at IS NULL",
            "text = %s",
            "scope = %s",
        ]
        args: list[Any] = [workspace_id, body, scope]
        if scope == "bot":
            if not bot_id:
                return None
            clauses.append("bot_id = %s")
            args.append(bot_id)
        with self._conn() as conn:
            row = conn.execute(
                f"""
                SELECT id, scope, kind, slot, text, source, bot_id, document_id, shelf, until
                FROM memory_entries
                WHERE {' AND '.join(clauses)}
                LIMIT 1
                """,
                args,
            ).fetchone()
            conn.commit()
        return self._entry_from_row(row) if row else None

    def find_entry_by_document(self, document_id: str) -> MemoryEntry | None:
        with self._conn() as conn:
            row = conn.execute(
                """
                SELECT id, scope, kind, slot, text, source, bot_id, document_id, shelf, until
                FROM memory_entries
                WHERE document_id = %s AND superseded_at IS NULL
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (document_id,),
            ).fetchone()
            conn.commit()
        return self._entry_from_row(row) if row else None

    def update_entry_text(self, entry_id: str, text: str) -> MemoryEntry | None:
        body = (text or "").strip()
        if not body:
            return None
        with self._conn() as conn:
            row = conn.execute(
                """
                UPDATE memory_entries
                SET text = %s
                WHERE id = %s
                RETURNING id, scope, kind, slot, text, source, bot_id, document_id, shelf, until
                """,
                (body, entry_id),
            ).fetchone()
            conn.commit()
        return self._entry_from_row(row) if row else None

    def supersede_memory_entry(self, entry_id: str) -> bool:
        with self._conn() as conn:
            row = conn.execute(
                """
                UPDATE memory_entries
                SET superseded_at = %s
                WHERE id = %s AND superseded_at IS NULL
                RETURNING document_id
                """,
                (isoformat_utc(), entry_id),
            ).fetchone()
            conn.commit()
        if row is None:
            return False
        document_id = row.get("document_id") if isinstance(row, dict) else row["document_id"]
        if document_id:
            self.delete_memory(document_id)
        return True

    def _entry_from_row(self, row: dict[str, Any]) -> MemoryEntry:
        until = row.get("until")
        if until is not None and hasattr(until, "isoformat"):
            until = until.isoformat()
        return MemoryEntry(
            id=row["id"],
            scope=row["scope"],
            kind=row["kind"],
            text=row["text"],
            source=row["source"],
            bot_id=row["bot_id"],
            document_id=row["document_id"],
            slot=row.get("slot"),
            shelf=str(row.get("shelf") or "owner"),
            until=str(until) if until else None,
        )

    def _memory_from_row(self, row: dict[str, Any]) -> MemoryDocument:
        return MemoryDocument(
            id=row["id"],
            scope=row["scope"],
            bot_id=row["bot_id"],
            path=row["path"],
            content=row["content"],
            revision=int(row["revision"]),
            updated_at=parse_iso(row["updated_at"]),
        )
