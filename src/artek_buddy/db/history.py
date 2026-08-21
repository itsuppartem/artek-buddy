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


class HistoryStore:
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

    def delete_bot(self, bot_id: str, delete_memories: bool = False) -> bool:
        bot = self.get_bot(bot_id)
        if bot is None:
            return False
        with self._conn() as conn:
            with conn.transaction():
                conn.execute(
                    "DELETE FROM memory_entries WHERE scope = 'bot' AND bot_id = %s",
                    (bot_id,),
                )
                conn.execute(
                    "DELETE FROM memory_documents WHERE scope = 'bot' AND bot_id = %s",
                    (bot_id,),
                )
                if not delete_memories:
                    safe_name = bot.name.replace("/", "-").strip() or "Bot"
                    archive_dir = f"bots/{safe_name}-{bot.id}"
                    conn.execute(
                        """
                        UPDATE memory_documents
                        SET bot_id = NULL,
                            scope = 'user',
                            path = %s || '/' || path,
                            updated_at = %s
                        WHERE bot_id = %s AND scope = 'user'
                        """,
                        (archive_dir, isoformat_utc(), bot_id),
                    )
                else:
                    conn.execute("DELETE FROM memory_documents WHERE bot_id = %s", (bot_id,))
                conn.execute("DELETE FROM consent_requests WHERE bot_id = %s", (bot_id,))
                conn.execute("DELETE FROM consent_grants WHERE bot_id = %s", (bot_id,))
                conn.execute("DELETE FROM routines WHERE bot_id = %s", (bot_id,))
                conn.execute("DELETE FROM turn_inbox WHERE bot_id = %s", (bot_id,))
                conn.execute("DELETE FROM subagents WHERE bot_id = %s", (bot_id,))
                conn.execute(
                    "UPDATE messages SET reply_to_id = NULL WHERE thread_id = %s",
                    (bot.thread_id,),
                )
                conn.execute("DELETE FROM messages WHERE thread_id = %s", (bot.thread_id,))
                conn.execute("DELETE FROM runs WHERE bot_id = %s", (bot_id,))
                conn.execute("DELETE FROM threads WHERE id = %s", (bot.thread_id,))
                conn.execute("DELETE FROM bots WHERE id = %s", (bot_id,))
                conn.execute(
                    """
                    DELETE FROM computers
                    WHERE NOT EXISTS (
                        SELECT 1 FROM bots WHERE bots.computer_id = computers.id
                    )
                    """
                )
        return True

    def archive_bot(self, bot_id: str) -> Bot | None:
        now = isoformat_utc()
        with self._conn() as conn:
            row = conn.execute(
                """
                UPDATE bots
                SET archived_at = %s, status = 'idle', updated_at = %s
                WHERE id = %s
                RETURNING *
                """,
                (now, now, bot_id),
            ).fetchone()
            conn.commit()
        return self._bot_from_row(row) if row else None

    def restore_bot(self, bot_id: str) -> Bot | None:
        now = isoformat_utc()
        with self._conn() as conn:
            row = conn.execute(
                """
                UPDATE bots
                SET archived_at = NULL, updated_at = %s
                WHERE id = %s
                RETURNING *
                """,
                (now, bot_id),
            ).fetchone()
            conn.commit()
        return self._bot_from_row(row) if row else None

    def duplicate_bot(self, bot_id: str) -> Bot:
        original = self.get_bot(bot_id)
        if original is None:
            raise ValueError(f"bot {bot_id} not found")
        return self.create_bot(
            name=f"{original.name} (Copy)",
            title=original.title,
            description=original.description,
            instructions=original.instructions,
            color=original.color,
            notify_on_finish=original.notify_on_finish,
            computer_mode=original.computer_mode,
            workspace_id=original.workspace_id,
        )

    def update_bot(
        self,
        bot_id: str,
        name: str | None = None,
        title: str | None = None,
        description: str | None = None,
        instructions: str | None = None,
        color: str | None = None,
        pinned: bool | None = None,
        notify_on_finish: bool | None = None,
        unread: bool | None = None,
        computer_mode: str | None = None,
    ) -> Bot | None:
        bot = self.get_bot(bot_id)
        if bot is None:
            return None
        now = isoformat_utc()
        new_name = bot.name if name is None else name.strip()
        new_title = bot.title if title is None else title
        new_description = bot.description if description is None else description
        new_instructions = bot.instructions if instructions is None else instructions
        new_color = bot.color if color is None else color
        new_pinned = bot.pinned if pinned is None else bool(pinned)
        new_notify = bot.notify_on_finish if notify_on_finish is None else bool(notify_on_finish)
        new_unread = bot.unread if unread is None else bool(unread)
        new_mode = (
            bot.computer_mode
            if computer_mode is None
            else ("dedicated" if computer_mode == "dedicated" else "team")
        )

        with self._conn() as conn:
            row = conn.execute(
                """
                UPDATE bots
                SET name = %s, title = %s, description = %s, instructions = %s,
                    color = %s, pinned = %s, notify_on_finish = %s, unread = %s,
                    computer_mode = %s, updated_at = %s
                WHERE id = %s
                RETURNING *
                """,
                (
                    new_name,
                    new_title,
                    new_description,
                    new_instructions,
                    new_color,
                    new_pinned,
                    new_notify,
                    new_unread,
                    new_mode,
                    now,
                    bot_id,
                ),
            ).fetchone()
            conn.commit()
        updated = self._bot_from_row(row) if row else None
        if updated is not None and computer_mode is not None and new_mode != bot.computer_mode:
            self.ensure_computer(updated)
            return self.get_bot(bot_id) or updated
        return updated

    def set_bot_unread(self, bot_id: str, unread: bool) -> Bot | None:
        now = isoformat_utc()
        with self._conn() as conn:
            row = conn.execute(
                """
                UPDATE bots
                SET unread = %s, updated_at = %s
                WHERE id = %s
                RETURNING *
                """,
                (unread, now, bot_id),
            ).fetchone()
            conn.commit()
        return self._bot_from_row(row) if row else None

    def cancel_active_runs(self, bot_id: str) -> list[str]:
        now = isoformat_utc()
        with self._conn() as conn:
            with conn.transaction():
                rows = conn.execute(
                    """
                    UPDATE runs
                    SET status = %s, completed_at = %s
                    WHERE bot_id = %s
                      AND status IN ('queued', 'leased', 'running', 'waiting_input', 'waiting_takeover')
                    RETURNING id
                    """,
                    (RunStatus.cancelled.value, now, bot_id),
                ).fetchall()
                conn.execute(
                    "UPDATE bots SET status = 'idle', updated_at = %s WHERE id = %s",
                    (now, bot_id),
                )
        return [row["id"] for row in rows]

    def fail_orphaned_runs(self, error: str = "The host restarted before this turn finished.") -> int:
        """Mark leftover in-flight work failed after a process restart."""
        now = isoformat_utc()
        with self._conn() as conn:
            with conn.transaction():
                rows = conn.execute(
                    """
                    UPDATE runs
                    SET status = %s, error = %s, completed_at = %s
                    WHERE status IN ('queued', 'leased', 'running', 'waiting_input', 'waiting_takeover')
                    RETURNING id, bot_id
                    """,
                    (RunStatus.failed.value, error, now),
                ).fetchall()
                bot_ids = [row["bot_id"] for row in rows]
                if bot_ids:
                    conn.execute(
                        """
                        UPDATE bots
                        SET status = 'idle', updated_at = %s
                        WHERE id = ANY(%s)
                        """,
                        (now, bot_ids),
                    )
                conn.execute(
                    """
                    UPDATE subagents
                    SET status = 'failed', error = %s, updated_at = %s
                    WHERE status IN ('queued', 'running')
                    """,
                    (error, now),
                )
        return len(rows)

    def create_bot(
        self,
        name: str,
        title: str = "",
        description: str = "",
        instructions: str = "",
        color: str | None = None,
        notify_on_finish: bool = True,
        computer_mode: str = "team",
        cursor_agent_id: str | None = None,
        workspace_id: str = DEFAULT_WORKSPACE_ID,
    ) -> Bot:
        bot_id = new_id("bot")
        thread_id = new_id("thr")
        now = isoformat_utc()
        if not color:
            count = self._bot_count()
            color = pick_color(count)
        mode = "dedicated" if computer_mode == "dedicated" else "team"
        with self._conn() as conn:
            with conn.transaction():
                conn.execute(
                    """
                    INSERT INTO workspaces (id) VALUES (%s)
                    ON CONFLICT (id) DO NOTHING
                    """,
                    (workspace_id,),
                )
                conn.execute(
                    """
                    INSERT INTO bots (
                        id, workspace_id, name, title, description, instructions,
                        color, notify_on_finish, pinned, archived_at, unread,
                        parent_bot_id, thread_id, preview, status, computer_mode,
                        cursor_agent_id, created_at, updated_at
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s,
                        %s, %s, FALSE, NULL, FALSE,
                        NULL, %s, '', 'idle', %s,
                        %s, %s, %s
                    )
                    """,
                    (
                        bot_id,
                        workspace_id,
                        name,
                        title,
                        description,
                        instructions,
                        color,
                        notify_on_finish,
                        thread_id,
                        mode,
                        cursor_agent_id,
                        now,
                        now,
                    ),
                )
                conn.execute(
                    """
                    INSERT INTO threads (id, bot_id, workspace_id, created_at)
                    VALUES (%s, %s, %s, %s)
                    """,
                    (thread_id, bot_id, workspace_id, now),
                )
        bot = self.get_bot(bot_id)
        if bot is None:
            raise RuntimeError("failed to create bot")
        self.ensure_computer(bot)
        refreshed = self.get_bot(bot_id)
        return refreshed or bot

    def attach_agent(self, bot_id: str, cursor_agent_id: str) -> Bot:
        with self._conn() as conn:
            conn.execute(
                """
                UPDATE bots
                SET cursor_agent_id = %s, updated_at = %s
                WHERE id = %s
                """,
                (cursor_agent_id, isoformat_utc(), bot_id),
            )
            conn.commit()
        bot = self.get_bot(bot_id)
        if bot is None:
            raise RuntimeError(f"bot {bot_id} missing after attach")
        return bot

    def list_bots(self) -> list[Bot]:
        with self._conn() as conn:
            rows = conn.execute(
                """
                SELECT * FROM bots
                WHERE archived_at IS NULL
                ORDER BY pinned DESC, updated_at DESC, created_at DESC
                """
            ).fetchall()
            conn.commit()
        return [self._bot_from_row(row) for row in rows]

    def list_archived_bots(self) -> list[Bot]:
        with self._conn() as conn:
            rows = conn.execute(
                """
                SELECT * FROM bots
                WHERE archived_at IS NOT NULL
                ORDER BY archived_at DESC, created_at DESC
                """
            ).fetchall()
            conn.commit()
        return [self._bot_from_row(row) for row in rows]

    def get_bot(self, bot_id: str) -> Bot | None:
        with self._conn() as conn:
            row = conn.execute("SELECT * FROM bots WHERE id = %s", (bot_id,)).fetchone()
            conn.commit()
        return self._bot_from_row(row) if row else None

    def get_bot_by_agent(self, cursor_agent_id: str) -> Bot | None:
        with self._conn() as conn:
            row = conn.execute(
                """
                SELECT * FROM bots
                WHERE cursor_agent_id = %s AND archived_at IS NULL
                ORDER BY updated_at DESC
                LIMIT 1
                """,
                (cursor_agent_id,),
            ).fetchone()
            conn.commit()
        return self._bot_from_row(row) if row else None

    def default_bot(self, cursor_agent_id: str | None = None) -> Bot | None:
        if cursor_agent_id:
            found = self.get_bot_by_agent(cursor_agent_id)
            if found is not None:
                return found
        bots = self.list_bots()
        return bots[0] if bots else None

    def page_messages(
        self,
        thread_id: str,
        before: int | None = None,
        limit: int = DEFAULT_PAGE_SIZE,
    ) -> ThreadMessagePage:
        limit = max(1, min(int(limit or DEFAULT_PAGE_SIZE), 200))
        with self._conn() as conn:
            if before is None:
                rows = conn.execute(
                    """
                    SELECT * FROM messages
                    WHERE thread_id = %s
                    ORDER BY seq DESC
                    LIMIT %s
                    """,
                    (thread_id, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT * FROM messages
                    WHERE thread_id = %s AND seq < %s
                    ORDER BY seq DESC
                    LIMIT %s
                    """,
                    (thread_id, before, limit),
                ).fetchall()
            conn.commit()
        rows = list(reversed(rows))
        messages = self._with_replies([self._message_from_row(row) for row in rows])
        cursor = older_cursor([item.seq for item in messages], page_limit=limit)
        if cursor is not None:
            with self._conn() as conn:
                older = conn.execute(
                    "SELECT 1 FROM messages WHERE thread_id = %s AND seq < %s LIMIT 1",
                    (thread_id, min(item.seq for item in messages)),
                ).fetchone()
                conn.commit()
            if older is None:
                cursor = None
        return ThreadMessagePage(
            thread_id=thread_id,
            messages=messages,
            older_cursor=cursor,
        )

    def latest_run(self, bot_id: str) -> Run | None:
        with self._conn() as conn:
            row = conn.execute(
                """
                SELECT * FROM runs
                WHERE bot_id = %s
                ORDER BY
                  CASE WHEN status IN (
                    'queued', 'leased', 'running', 'waiting_input', 'waiting_takeover'
                  ) THEN 0 ELSE 1 END,
                  started_at DESC NULLS LAST,
                  id DESC
                LIMIT 1
                """,
                (bot_id,),
            ).fetchone()
            conn.commit()
        return self._run_from_row(row) if row else None

    def active_run_count(self, bot_id: str) -> int:
        with self._conn() as conn:
            row = conn.execute(
                """
                SELECT COUNT(*) AS n FROM runs
                WHERE bot_id = %s
                  AND status IN (
                    'queued', 'leased', 'running', 'waiting_input', 'waiting_takeover'
                  )
                """,
                (bot_id,),
            ).fetchone()
            conn.commit()
        return int(row["n"]) if row else 0

    def get_message_in_thread(self, thread_id: str, message_id: str) -> ThreadMessage | None:
        with self._conn() as conn:
            row = conn.execute(
                """
                SELECT * FROM messages
                WHERE id = %s AND thread_id = %s
                """,
                (message_id, thread_id),
            ).fetchone()
            conn.commit()
        if row is None:
            return None
        return self._with_replies([self._message_from_row(row)])[0]

    def latest_seq(self, thread_id: str) -> int:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT COALESCE(MAX(seq), -1) AS max_seq FROM messages WHERE thread_id = %s",
                (thread_id,),
            ).fetchone()
            conn.commit()
        value = -1 if row is None else int(row["max_seq"])
        return value

    def begin_or_enqueue_turn(
        self,
        bot: Bot,
        text: str,
        *,
        model_provider: str | None = "cursor",
        model_id: str | None = None,
        trigger: str = "user",
        reply_to_id: str | None = None,
        max_inbox: int = 20,
        blocks: list[dict[str, Any]] | None = None,
        preview: str | None = None,
    ) -> tuple[ThreadMessage, Run, bool]:
        """Atomically start a lead turn or queue behind the current lead."""
        message_blocks = blocks or text_blocks(text)
        preview_text = preview or text
        with self._conn() as conn:
            with conn.transaction():
                locked = conn.execute(
                    "SELECT id FROM bots WHERE id = %s FOR UPDATE",
                    (bot.id,),
                ).fetchone()
                if locked is None:
                    raise RuntimeError("bot not found")
                active = conn.execute(
                    """
                    SELECT * FROM runs
                    WHERE bot_id = %s
                      AND status IN ('queued', 'leased', 'running', 'waiting_input', 'waiting_takeover')
                    ORDER BY started_at DESC
                    LIMIT 1
                    FOR UPDATE
                    """,
                    (bot.id,),
                ).fetchone()
                if active is not None and active["status"] == "waiting_takeover":
                    conn.execute(
                        """
                        UPDATE runs
                        SET status = %s, error = %s, completed_at = %s
                        WHERE id = %s
                        """,
                        (
                            RunStatus.cancelled.value,
                            "Stopped.",
                            isoformat_utc(),
                            active["id"],
                        ),
                    )
                    active = None
                now = isoformat_utc()
                seq = self._lock_next_seq(conn, bot.thread_id)
                msg_id = new_id("msg")
                if active is not None:
                    queued = conn.execute(
                        "SELECT COUNT(*) AS n FROM turn_inbox WHERE bot_id = %s",
                        (bot.id,),
                    ).fetchone()
                    if int(queued["n"]) >= max_inbox:
                        raise InboxFullError(
                            "Too many messages are already queued. Wait for the bot to finish, then try again."
                        )
                    conn.execute(
                        """
                        INSERT INTO messages (
                            id, thread_id, seq, role, blocks, run_id, reply_to_id, created_at
                        )
                        VALUES (%s, %s, %s, %s, %s, NULL, %s, %s)
                        """,
                        (
                            msg_id,
                            bot.thread_id,
                            seq,
                            MessageRole.user.value,
                            Json(message_blocks),
                            reply_to_id,
                            now,
                        ),
                    )
                    conn.execute(
                        """
                        INSERT INTO turn_inbox (id, bot_id, message_id, text, reply_to_id, created_at)
                        VALUES (%s, %s, %s, %s, %s, %s)
                        """,
                        (new_id("inb"), bot.id, msg_id, text, reply_to_id, now),
                    )
                    conn.execute(
                        "UPDATE bots SET preview = %s, unread = FALSE, updated_at = %s WHERE id = %s",
                        (preview_snippet(preview_text), now, bot.id),
                    )
                    run_id = active["id"]
                    queued_turn = True
                else:
                    run_id = new_id("run")
                    task_id = new_id("tsk")
                    conn.execute(
                        """
                        INSERT INTO messages (
                            id, thread_id, seq, role, blocks, run_id, reply_to_id, created_at
                        )
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                        """,
                        (
                            msg_id,
                            bot.thread_id,
                            seq,
                            MessageRole.user.value,
                            Json(message_blocks),
                            run_id,
                            reply_to_id,
                            now,
                        ),
                    )
                    conn.execute(
                        """
                        INSERT INTO runs (
                            id, bot_id, thread_id, task_id, status, trigger,
                            model_provider, model_id, error, result, started_at, completed_at
                        ) VALUES (
                            %s, %s, %s, %s, %s, %s,
                            %s, %s, NULL, NULL, %s, NULL
                        )
                        """,
                        (
                            run_id,
                            bot.id,
                            bot.thread_id,
                            task_id,
                            RunStatus.running.value,
                            trigger or "user",
                            model_provider,
                            model_id,
                            now,
                        ),
                    )
                    conn.execute(
                        """
                        UPDATE bots
                        SET preview = %s, status = %s, unread = FALSE, updated_at = %s
                        WHERE id = %s
                        """,
                        (preview_snippet(preview_text), "running", now, bot.id),
                    )
                    queued_turn = False
        user = self._get_message(msg_id)
        run = self._get_run(run_id)
        if user is None or run is None:
            raise RuntimeError("failed to persist turn")
        return self._with_replies([user])[0], run, queued_turn

    def begin_turn(
        self,
        bot: Bot,
        text: str,
        model_provider: str | None = "cursor",
        model_id: str | None = None,
        trigger: str = "user",
        reply_to_id: str | None = None,
    ) -> tuple[ThreadMessage, Run]:
        with self._conn() as conn:
            with conn.transaction():
                seq = self._lock_next_seq(conn, bot.thread_id)
                msg_id = new_id("msg")
                run_id = new_id("run")
                task_id = new_id("tsk")
                now = isoformat_utc()
                blocks = text_blocks(text)
                conn.execute(
                    """
                    INSERT INTO messages (
                        id, thread_id, seq, role, blocks, run_id, reply_to_id, created_at
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        msg_id,
                        bot.thread_id,
                        seq,
                        MessageRole.user.value,
                        Json(blocks),
                        run_id,
                        reply_to_id,
                        now,
                    ),
                )
                conn.execute(
                    """
                    INSERT INTO runs (
                        id, bot_id, thread_id, task_id, status, trigger,
                        model_provider, model_id, error, result, started_at, completed_at
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s,
                        %s, %s, NULL, NULL, %s, NULL
                    )
                    """,
                    (
                        run_id,
                        bot.id,
                        bot.thread_id,
                        task_id,
                        RunStatus.running.value,
                        trigger or "user",
                        model_provider,
                        model_id,
                        now,
                    ),
                )
                conn.execute(
                    """
                    UPDATE bots
                    SET preview = %s, status = %s, unread = FALSE, updated_at = %s
                    WHERE id = %s
                    """,
                    (preview_snippet(text), "running", now, bot.id),
                )
        user = self._get_message(msg_id)
        run = self._get_run(run_id)
        if user is None or run is None:
            raise RuntimeError("failed to persist turn start")
        return self._with_replies([user])[0], run

    def finish_turn(
        self,
        bot: Bot,
        run: Run,
        text: str,
        status: str,
        error: str | None = None,
    ) -> tuple[ThreadMessage | None, Run]:
        if status not in {item.value for item in RunStatus}:
            status = RunStatus.failed.value
        msg_id: str | None = None
        with self._conn() as conn:
            with conn.transaction():
                already = conn.execute(
                    "SELECT status FROM runs WHERE id = %s FOR UPDATE",
                    (run.id,),
                ).fetchone()
                if not (
                    already
                    and already["status"] == RunStatus.cancelled.value
                    and status != RunStatus.cancelled.value
                ):
                    now = isoformat_utc()
                    body = (text or "").strip() if text else ""
                    if not body and error and status != RunStatus.cancelled.value:
                        body = error
                    if body:
                        seq = self._lock_next_seq(conn, bot.thread_id)
                        msg_id = new_id("msg")
                        blocks = text_blocks(body)
                        conn.execute(
                            """
                            INSERT INTO messages (id, thread_id, seq, role, blocks, run_id, created_at)
                            VALUES (%s, %s, %s, %s, %s, %s, %s)
                            """,
                            (msg_id, bot.thread_id, seq, MessageRole.bot.value, Json(blocks), run.id, now),
                        )
                    conn.execute(
                        """
                        UPDATE runs
                        SET status = %s, error = %s, result = %s, completed_at = %s
                        WHERE id = %s
                        """,
                        (status, error, text or None, now, run.id),
                    )
                    still = conn.execute(
                        """
                        SELECT 1 FROM runs
                        WHERE bot_id = %s
                          AND id <> %s
                          AND status IN (
                            'queued', 'leased', 'running', 'waiting_input', 'waiting_takeover'
                          )
                        LIMIT 1
                        """,
                        (bot.id, run.id),
                    ).fetchone()
                    if still:
                        bot_status = "running"
                    elif status in {RunStatus.completed.value, RunStatus.cancelled.value}:
                        bot_status = "idle"
                    else:
                        bot_status = "error"
                    if body:
                        conn.execute(
                            """
                            UPDATE bots
                            SET preview = %s, status = %s, unread = TRUE, updated_at = %s
                            WHERE id = %s
                            """,
                            (preview_snippet(body), bot_status, now, bot.id),
                        )
                    else:
                        conn.execute(
                            """
                            UPDATE bots
                            SET status = %s, updated_at = %s
                            WHERE id = %s
                            """,
                            (bot_status, now, bot.id),
                        )
        message = self._get_message(msg_id) if msg_id else None
        finished = self._get_run(run.id)
        if finished is None:
            raise RuntimeError("failed to persist turn finish")
        return message, finished

    def append_bot_message(
        self,
        bot: Bot,
        blocks: list[dict[str, Any]],
        run_id: str | None = None,
        reply_to_id: str | None = None,
    ) -> ThreadMessage:
        with self._conn() as conn:
            with conn.transaction():
                seq = self._lock_next_seq(conn, bot.thread_id)
                msg_id = new_id("msg")
                now = isoformat_utc()
                conn.execute(
                    """
                    INSERT INTO messages (
                        id, thread_id, seq, role, blocks, run_id, reply_to_id, created_at
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        msg_id,
                        bot.thread_id,
                        seq,
                        MessageRole.bot.value,
                        Json(blocks),
                        run_id,
                        reply_to_id,
                        now,
                    ),
                )
                excerpt = ""
                for b in blocks:
                    if not isinstance(b, dict):
                        continue
                    if b.get("text"):
                        excerpt = str(b["text"])
                        break
                if not excerpt:
                    for b in blocks:
                        if isinstance(b, dict) and b.get("kind") == "file" and b.get("name"):
                            excerpt = str(b["name"])
                            break
                if excerpt:
                    conn.execute(
                        "UPDATE bots SET preview = %s, unread = TRUE, updated_at = %s WHERE id = %s",
                        (preview_snippet(excerpt), now, bot.id),
                    )
        message = self._get_message(msg_id)
        if message is None:
            raise RuntimeError("failed to persist bot message")
        return self._with_replies([message])[0]

    def save_artifact(
        self,
        *,
        bot_id: str,
        name: str,
        mime_type: str,
        size: int,
        storage_path: str,
        run_id: str | None = None,
        artifact_id: str | None = None,
    ) -> Artifact:
        artifact_id = artifact_id or new_id("art")
        now = isoformat_utc()
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO artifacts (
                    id, bot_id, run_id, name, mime_type, size, storage_path, created_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (artifact_id, bot_id, run_id, name, mime_type, size, storage_path, now),
            )
            conn.commit()
        return Artifact(
            id=artifact_id,
            bot_id=bot_id,
            run_id=run_id,
            name=name,
            mime_type=mime_type,
            size=size,
            created_at=now,
        )

    def get_artifact(self, artifact_id: str) -> tuple[Artifact, str] | None:
        with self._conn() as conn:
            row = conn.execute("SELECT * FROM artifacts WHERE id = %s", (artifact_id,)).fetchone()
            conn.commit()
        if row is None:
            return None
        return self._artifact_from_row(row), str(row["storage_path"])

    def list_artifacts(self, bot_id: str) -> list[Artifact]:
        with self._conn() as conn:
            rows = conn.execute(
                """
                SELECT * FROM artifacts
                WHERE bot_id = %s
                ORDER BY created_at DESC
                """,
                (bot_id,),
            ).fetchall()
            conn.commit()
        return [self._artifact_from_row(row) for row in rows]

    def _artifact_from_row(self, row: dict[str, Any]) -> Artifact:
        return Artifact(
            id=row["id"],
            bot_id=row["bot_id"],
            run_id=row.get("run_id"),
            name=row["name"],
            mime_type=row["mime_type"],
            size=int(row["size"] or 0),
            created_at=parse_iso(row["created_at"]),
        )

    def append_user_message(
        self,
        bot: Bot,
        text: str,
        reply_to_id: str | None = None,
    ) -> ThreadMessage:
        with self._conn() as conn:
            with conn.transaction():
                seq = self._lock_next_seq(conn, bot.thread_id)
                msg_id = new_id("msg")
                now = isoformat_utc()
                conn.execute(
                    """
                    INSERT INTO messages (
                        id, thread_id, seq, role, blocks, run_id, reply_to_id, created_at
                    )
                    VALUES (%s, %s, %s, %s, %s, NULL, %s, %s)
                    """,
                    (
                        msg_id,
                        bot.thread_id,
                        seq,
                        MessageRole.user.value,
                        Json(text_blocks(text)),
                        reply_to_id,
                        now,
                    ),
                )
                conn.execute(
                    "UPDATE bots SET preview = %s, unread = FALSE, updated_at = %s WHERE id = %s",
                    (preview_snippet(text), now, bot.id),
                )
        message = self._get_message(msg_id)
        if message is None:
            raise RuntimeError("failed to persist inbox message")
        return self._with_replies([message])[0]

    def answer_pending_asks(self, thread_id: str, answer: str) -> list[ThreadMessage]:
        text = (answer or "").strip()
        if not text:
            return []
        updated_ids: list[str] = []
        with self._conn() as conn:
            with conn.transaction():
                rows = conn.execute(
                    """
                    SELECT id, blocks
                    FROM messages
                    WHERE thread_id = %s AND role = %s
                    ORDER BY seq DESC
                    LIMIT 30
                    """,
                    (thread_id, MessageRole.bot.value),
                ).fetchall()
                for row in rows:
                    blocks = row["blocks"]
                    if isinstance(blocks, str):
                        import json

                        blocks = json.loads(blocks)
                    if not isinstance(blocks, list):
                        continue
                    next_blocks, changed = answer_ask_blocks(blocks, text)
                    if not changed:
                        continue
                    conn.execute(
                        "UPDATE messages SET blocks = %s WHERE id = %s",
                        (Json(next_blocks), row["id"]),
                    )
                    updated_ids.append(row["id"])
                    break
        out: list[ThreadMessage] = []
        for message_id in updated_ids:
            message = self._get_message(message_id)
            if message is not None:
                out.append(message)
        return out

    def answer_message_ask(self, message_id: str, answer: str) -> ThreadMessage | None:
        text = (answer or "").strip()
        if not text:
            return None
        with self._conn() as conn:
            row = conn.execute(
                "SELECT id, blocks FROM messages WHERE id = %s",
                (message_id,),
            ).fetchone()
            if row is None:
                conn.commit()
                return None
            blocks = row["blocks"]
            if isinstance(blocks, str):
                import json

                blocks = json.loads(blocks)
            next_blocks, changed = answer_ask_blocks(
                blocks if isinstance(blocks, list) else [],
                text,
                include_consent=True,
            )
            if changed:
                conn.execute(
                    "UPDATE messages SET blocks = %s WHERE id = %s",
                    (Json(next_blocks), message_id),
                )
            conn.commit()
        return self._get_message(message_id)

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

    def enqueue_inbox(
        self,
        bot_id: str,
        message_id: str,
        text: str,
        reply_to_id: str | None = None,
    ) -> None:
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO turn_inbox (id, bot_id, message_id, text, reply_to_id, created_at)
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (new_id("inb"), bot_id, message_id, text, reply_to_id, isoformat_utc()),
            )
            conn.commit()

    def inbox_count(self, bot_id: str) -> int:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS n FROM turn_inbox WHERE bot_id = %s",
                (bot_id,),
            ).fetchone()
            conn.commit()
        return int(row["n"]) if row else 0

    def clear_inbox(self, bot_id: str) -> None:
        with self._conn() as conn:
            conn.execute("DELETE FROM turn_inbox WHERE bot_id = %s", (bot_id,))
            conn.commit()

    def drain_inbox(self, bot_id: str) -> list[dict[str, str | None]]:
        with self._conn() as conn:
            with conn.transaction():
                rows = conn.execute(
                    """
                    SELECT id, message_id, text, reply_to_id
                    FROM turn_inbox
                    WHERE bot_id = %s
                    ORDER BY created_at ASC
                    FOR UPDATE
                    """,
                    (bot_id,),
                ).fetchall()
                if rows:
                    conn.execute("DELETE FROM turn_inbox WHERE bot_id = %s", (bot_id,))
        return [
            {
                "message_id": row["message_id"],
                "text": row["text"],
                "reply_to_id": row["reply_to_id"],
            }
            for row in rows
        ]

    def claim_inbox_follow_up(
        self,
        bot: Bot,
        *,
        model_provider: str | None = "cursor",
        model_id: str | None = None,
    ) -> tuple[Run, list[dict[str, str | None]]] | None:
        """Atomically claim queued messages only when no other lead is active."""
        with self._conn() as conn:
            with conn.transaction():
                locked = conn.execute(
                    "SELECT id FROM bots WHERE id = %s FOR UPDATE",
                    (bot.id,),
                ).fetchone()
                if locked is None:
                    return None
                active = conn.execute(
                    """
                    SELECT 1 FROM runs
                    WHERE bot_id = %s
                      AND status IN ('queued', 'leased', 'running', 'waiting_input', 'waiting_takeover')
                    LIMIT 1
                    """,
                    (bot.id,),
                ).fetchone()
                if active is not None:
                    return None
                rows = conn.execute(
                    """
                    SELECT id, message_id, text, reply_to_id
                    FROM turn_inbox
                    WHERE bot_id = %s
                    ORDER BY created_at ASC
                    FOR UPDATE
                    """,
                    (bot.id,),
                ).fetchall()
                if not rows:
                    return None
                now = isoformat_utc()
                run_id = new_id("run")
                task_id = new_id("tsk")
                conn.execute(
                    """
                    INSERT INTO runs (
                        id, bot_id, thread_id, task_id, status, trigger,
                        model_provider, model_id, error, result, started_at, completed_at
                    ) VALUES (
                        %s, %s, %s, %s, %s, 'follow_up',
                        %s, %s, NULL, NULL, %s, NULL
                    )
                    """,
                    (
                        run_id,
                        bot.id,
                        bot.thread_id,
                        task_id,
                        RunStatus.running.value,
                        model_provider,
                        model_id,
                        now,
                    ),
                )
                conn.execute("DELETE FROM turn_inbox WHERE bot_id = %s", (bot.id,))
                conn.execute(
                    "UPDATE bots SET status = %s, updated_at = %s WHERE id = %s",
                    ("running", now, bot.id),
                )
        run = self._get_run(run_id)
        if run is None:
            raise RuntimeError("failed to persist follow-up run")
        return (
            run,
            [
                {
                    "message_id": row["message_id"],
                    "text": row["text"],
                    "reply_to_id": row["reply_to_id"],
                }
                for row in rows
            ],
        )

    def begin_run(
        self,
        bot: Bot,
        trigger: str = "follow_up",
        model_provider: str | None = "cursor",
        model_id: str | None = None,
    ) -> Run:
        with self._conn() as conn:
            with conn.transaction():
                run_id = new_id("run")
                task_id = new_id("tsk")
                now = isoformat_utc()
                conn.execute(
                    """
                    INSERT INTO runs (
                        id, bot_id, thread_id, task_id, status, trigger,
                        model_provider, model_id, error, result, started_at, completed_at
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s,
                        %s, %s, NULL, NULL, %s, NULL
                    )
                    """,
                    (
                        run_id,
                        bot.id,
                        bot.thread_id,
                        task_id,
                        RunStatus.running.value,
                        trigger or "follow_up",
                        model_provider,
                        model_id,
                        now,
                    ),
                )
                conn.execute(
                    "UPDATE bots SET status = %s, updated_at = %s WHERE id = %s",
                    ("running", now, bot.id),
                )
        run = self._get_run(run_id)
        if run is None:
            raise RuntimeError("failed to persist follow-up run")
        return run

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

    def _lock_next_seq(self, conn: Any, thread_id: str) -> int:
        locked = conn.execute(
            "SELECT id FROM threads WHERE id = %s FOR UPDATE",
            (thread_id,),
        ).fetchone()
        if locked is None:
            raise RuntimeError(f"thread {thread_id} missing")
        row = conn.execute(
            "SELECT MAX(seq) AS max_seq FROM messages WHERE thread_id = %s",
            (thread_id,),
        ).fetchone()
        current = None if row is None or row["max_seq"] is None else int(row["max_seq"])
        return next_seq(current)

    def _bot_count(self) -> int:
        with self._conn() as conn:
            row = conn.execute("SELECT COUNT(*) AS n FROM bots").fetchone()
            conn.commit()
        return int(row["n"]) if row else 0

    def _get_message(self, message_id: str) -> ThreadMessage | None:
        with self._conn() as conn:
            row = conn.execute("SELECT * FROM messages WHERE id = %s", (message_id,)).fetchone()
            conn.commit()
        return self._message_from_row(row) if row else None

    def _get_run(self, run_id: str) -> Run | None:
        with self._conn() as conn:
            row = conn.execute("SELECT * FROM runs WHERE id = %s", (run_id,)).fetchone()
            conn.commit()
        return self._run_from_row(row) if row else None

    def _bot_from_row(self, row: dict[str, Any]) -> Bot:
        return Bot(
            id=row["id"],
            workspace_id=row["workspace_id"],
            name=row["name"],
            title=row["title"] or "",
            description=row["description"] or "",
            instructions=row["instructions"] or "",
            color=row["color"] or DEFAULT_BOT_COLOR,
            notify_on_finish=bool(row["notify_on_finish"]),
            pinned=bool(row["pinned"]),
            archived_at=parse_iso(row["archived_at"]) if row["archived_at"] else None,
            unread=bool(row["unread"]),
            parent_bot_id=row["parent_bot_id"],
            thread_id=row["thread_id"],
            preview=row["preview"] or "",
            status=row["status"] or "idle",
            computer_mode="dedicated" if row["computer_mode"] == "dedicated" else "team",
            cursor_agent_id=row.get("cursor_agent_id"),
            updated_at=parse_iso(row["updated_at"]),
            created_at=parse_iso(row["created_at"]),
        )

    def _message_from_row(self, row: dict[str, Any]) -> ThreadMessage:
        blocks = row["blocks"]
        if isinstance(blocks, str):
            import json

            blocks = json.loads(blocks)
        return ThreadMessage(
            id=row["id"],
            thread_id=row["thread_id"],
            seq=int(row["seq"]),
            role=row["role"],
            blocks=blocks or [],
            created_at=parse_iso(row["created_at"]),
            run_id=row["run_id"],
            reply_to_id=row.get("reply_to_id"),
        )

    def _with_replies(self, messages: list[ThreadMessage]) -> list[ThreadMessage]:
        ids = [item.reply_to_id for item in messages if item.reply_to_id]
        if not ids:
            return messages
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM messages WHERE id = ANY(%s)",
                (ids,),
            ).fetchall()
            conn.commit()
        by_id = {row["id"]: self._message_from_row(row) for row in rows}
        attached: list[ThreadMessage] = []
        for item in messages:
            target = by_id.get(item.reply_to_id or "")
            if target is None:
                attached.append(item)
                continue
            attached.append(
                item.model_copy(
                    update={
                        "reply_to": MessageReplyRef(
                            id=target.id,
                            role=target.role,
                            excerpt=preview_snippet(self._blocks_excerpt(target), 160),
                        )
                    }
                )
            )
        return attached

    def _blocks_excerpt(self, message: ThreadMessage) -> str:
        raw: list[dict[str, Any]] = []
        for block in message.blocks or []:
            if hasattr(block, "model_dump"):
                raw.append(block.model_dump())
            elif isinstance(block, dict):
                raw.append(block)
        return blocks_text(raw)

    def _run_from_row(self, row: dict[str, Any]) -> Run:
        return Run(
            id=row["id"],
            bot_id=row["bot_id"],
            thread_id=row["thread_id"],
            task_id=row["task_id"],
            status=row["status"],
            trigger=row["trigger"],
            model_provider=row["model_provider"],
            model_id=row["model_id"],
            error=row["error"],
            started_at=parse_iso(row["started_at"]) if row["started_at"] else None,
            completed_at=parse_iso(row["completed_at"]) if row["completed_at"] else None,
        )

    def create_pairing_code(self) -> PairingCode:
        code = new_pairing_code()
        now = datetime.now(timezone.utc)
        expires = now + timedelta(seconds=PAIRING_TTL_SECONDS)
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO device_pairing_codes (code_hash, expires_at, created_at)
                VALUES (%s, %s, %s)
                """,
                (hash_secret(normalize_pairing_code(code)), expires, now),
            )
            conn.commit()
        return PairingCode(code=code, expires_at=isoformat_utc(expires))

    def consume_pairing_code(self, code: str) -> bool:
        normalized = normalize_pairing_code(code)
        if len(normalized) < 8:
            return False
        with self._conn() as conn:
            row = conn.execute(
                """
                UPDATE device_pairing_codes
                SET used_at = now()
                WHERE code_hash = %s
                  AND used_at IS NULL
                  AND expires_at > now()
                RETURNING code_hash
                """,
                (hash_secret(normalized),),
            ).fetchone()
            conn.commit()
        return row is not None

    def create_device(self, name: str, platform: str = "linux") -> DeviceCreated:
        token = new_device_token()
        now = isoformat_utc()
        device_id = new_id("dev")
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO devices (id, name, platform, token_hash, created_at)
                VALUES (%s, %s, %s, %s, %s)
                """,
                (device_id, name.strip(), platform.strip() or "linux", hash_secret(token), now),
            )
            conn.commit()
        return DeviceCreated(
            id=device_id,
            name=name.strip(),
            platform=platform.strip() or "linux",
            created_at=now,
            token=token,
        )

    def list_devices(self) -> list[Device]:
        with self._conn() as conn:
            rows = conn.execute(
                """
                SELECT id, name, platform, created_at, last_seen_at, revoked_at
                FROM devices
                ORDER BY created_at DESC
                """
            ).fetchall()
            conn.commit()
        return [self._device_from_row(row) for row in rows]

    def get_device(self, device_id: str) -> Device | None:
        with self._conn() as conn:
            row = conn.execute(
                """
                SELECT id, name, platform, created_at, last_seen_at, revoked_at
                FROM devices WHERE id = %s
                """,
                (device_id,),
            ).fetchone()
            conn.commit()
        return self._device_from_row(row) if row else None

    def lookup_device_token(self, token: str) -> Device | None:
        if not token:
            return None
        with self._conn() as conn:
            row = conn.execute(
                """
                SELECT id, name, platform, created_at, last_seen_at, revoked_at
                FROM devices
                WHERE token_hash = %s AND revoked_at IS NULL
                """,
                (hash_secret(token),),
            ).fetchone()
            if row is None:
                conn.commit()
                return None
            seen = isoformat_utc()
            conn.execute(
                "UPDATE devices SET last_seen_at = %s WHERE id = %s",
                (seen, row["id"]),
            )
            conn.commit()
        device = self._device_from_row(row)
        return device.model_copy(update={"last_seen_at": seen})

    def revoke_device(self, device_id: str) -> Device | None:
        now = isoformat_utc()
        with self._conn() as conn:
            row = conn.execute(
                """
                UPDATE devices
                SET revoked_at = COALESCE(revoked_at, %s)
                WHERE id = %s AND revoked_at IS NULL
                RETURNING id, name, platform, created_at, last_seen_at, revoked_at
                """,
                (now, device_id),
            ).fetchone()
            conn.commit()
        return self._device_from_row(row) if row else None

    def delete_device(self, device_id: str) -> bool:
        with self._conn() as conn:
            row = conn.execute(
                "DELETE FROM devices WHERE id = %s RETURNING id",
                (device_id,),
            ).fetchone()
            conn.commit()
        return row is not None

    def delete_pairing_hash(self, code_hash: str) -> None:
        with self._conn() as conn:
            conn.execute("DELETE FROM device_pairing_codes WHERE code_hash = %s", (code_hash,))
            conn.commit()

    def _device_from_row(self, row: dict[str, Any]) -> Device:
        return Device(
            id=row["id"],
            name=row["name"],
            platform=row["platform"] or "linux",
            created_at=parse_iso(row["created_at"]),
            last_seen_at=parse_iso(row["last_seen_at"]) if row["last_seen_at"] else None,
            revoked_at=parse_iso(row["revoked_at"]) if row["revoked_at"] else None,
        )

    def create_routine(
        self,
        bot_id: str,
        name: str,
        prompt: str,
        cron: str,
        timezone_name: str = "UTC",
        notify: bool = True,
        active: bool = False,
    ) -> Routine:
        parse_cron(cron)
        zone = validate_timezone(timezone_name)
        now = datetime.now(timezone.utc)
        nxt = isoformat_utc(next_run_at(cron, now, zone)) if active else None
        routine_id = new_id("rtn")
        created = isoformat_utc(now)
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO routines (
                    id, bot_id, name, prompt, cron, timezone, active, notify,
                    last_run_at, next_run_at, created_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, NULL, %s, %s)
                """,
                (routine_id, bot_id, name.strip(), prompt, cron.strip(), zone, active, notify, nxt, created),
            )
            conn.commit()
        return Routine(
            id=routine_id,
            bot_id=bot_id,
            name=name.strip(),
            prompt=prompt,
            cron=cron.strip(),
            timezone=zone,
            active=active,
            notify=notify,
            last_run_at=None,
            next_run_at=nxt,
            created_at=created,
        )

    def list_routines(self, bot_id: str) -> list[Routine]:
        with self._conn() as conn:
            rows = conn.execute(
                """
                SELECT id, bot_id, name, prompt, cron, timezone, active, notify,
                       last_run_at, next_run_at, created_at
                FROM routines
                WHERE bot_id = %s
                ORDER BY created_at DESC
                """,
                (bot_id,),
            ).fetchall()
            conn.commit()
        return [self._routine_from_row(row) for row in rows]

    def get_routine(self, routine_id: str) -> Routine | None:
        with self._conn() as conn:
            row = conn.execute(
                """
                SELECT id, bot_id, name, prompt, cron, timezone, active, notify,
                       last_run_at, next_run_at, created_at
                FROM routines WHERE id = %s
                """,
                (routine_id,),
            ).fetchone()
            conn.commit()
        return self._routine_from_row(row) if row else None

    def update_routine(
        self,
        routine_id: str,
        name: str | None = None,
        prompt: str | None = None,
        cron: str | None = None,
        timezone_name: str | None = None,
        notify: bool | None = None,
        active: bool | None = None,
    ) -> Routine | None:
        current = self.get_routine(routine_id)
        if current is None:
            return None
        next_name = name.strip() if name is not None else current.name
        next_prompt = prompt if prompt is not None else current.prompt
        next_cron = cron.strip() if cron is not None else current.cron
        next_zone = validate_timezone(timezone_name) if timezone_name is not None else current.timezone
        next_notify = current.notify if notify is None else notify
        next_active = current.active if active is None else active
        parse_cron(next_cron)
        nxt = isoformat_utc(next_run_at(next_cron, datetime.now(timezone.utc), next_zone)) if next_active else None
        with self._conn() as conn:
            row = conn.execute(
                """
                UPDATE routines
                SET name = %s, prompt = %s, cron = %s, timezone = %s,
                    notify = %s, active = %s, next_run_at = %s
                WHERE id = %s
                RETURNING id, bot_id, name, prompt, cron, timezone, active, notify,
                          last_run_at, next_run_at, created_at
                """,
                (
                    next_name,
                    next_prompt,
                    next_cron,
                    next_zone,
                    next_notify,
                    next_active,
                    nxt,
                    routine_id,
                ),
            ).fetchone()
            conn.commit()
        return self._routine_from_row(row) if row else None

    def delete_routine(self, routine_id: str) -> bool:
        with self._conn() as conn:
            row = conn.execute(
                "DELETE FROM routines WHERE id = %s RETURNING id",
                (routine_id,),
            ).fetchone()
            conn.commit()
        return row is not None

    def claim_due_routines(self, limit: int = 20) -> list[Routine]:
        now = datetime.now(timezone.utc)
        lease_until = now + timedelta(minutes=5)
        claimed: list[Routine] = []
        with self._conn() as conn:
            rows = conn.execute(
                """
                SELECT id, bot_id, name, prompt, cron, timezone, active, notify,
                       last_run_at, next_run_at, created_at
                FROM routines
                WHERE active
                  AND next_run_at IS NOT NULL
                  AND next_run_at <= %s
                  AND (lease_until IS NULL OR lease_until <= %s)
                ORDER BY next_run_at
                LIMIT %s
                FOR UPDATE SKIP LOCKED
                """,
                (now, now, limit),
            ).fetchall()
            for row in rows:
                try:
                    parse_cron(row["cron"])
                except CronError:
                    conn.execute(
                        "UPDATE routines SET active = FALSE, lease_until = NULL WHERE id = %s",
                        (row["id"],),
                    )
                    continue
                seen = isoformat_utc(now)
                conn.execute(
                    """
                    UPDATE routines
                    SET last_run_at = %s, lease_until = %s
                    WHERE id = %s
                    """,
                    (seen, isoformat_utc(lease_until), row["id"]),
                )
                claimed.append(
                    self._routine_from_row(row).model_copy(update={"last_run_at": seen})
                )
            conn.commit()
        return claimed

    def ack_routine(self, routine_id: str) -> None:
        now = datetime.now(timezone.utc)
        with self._conn() as conn:
            row = conn.execute(
                "SELECT cron, timezone FROM routines WHERE id = %s AND active",
                (routine_id,),
            ).fetchone()
            if row is None:
                conn.commit()
                return
            try:
                nxt = next_run_at(row["cron"], now, row["timezone"] or "UTC")
            except CronError:
                conn.execute(
                    "UPDATE routines SET active = FALSE, lease_until = NULL WHERE id = %s",
                    (routine_id,),
                )
                conn.commit()
                return
            conn.execute(
                """
                UPDATE routines
                SET next_run_at = %s, lease_until = NULL
                WHERE id = %s
                """,
                (isoformat_utc(nxt), routine_id),
            )
            conn.commit()

    def reschedule_routine(self, routine_id: str, when: str) -> None:
        with self._conn() as conn:
            conn.execute(
                """
                UPDATE routines
                SET next_run_at = %s, lease_until = NULL
                WHERE id = %s AND active
                """,
                (when, routine_id),
            )
            conn.commit()

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

    def ensure_computer(self, bot: Bot) -> ComputerRecord:
        if bot.computer_mode == "dedicated":
            scope, scope_key, home_key = "dedicated", f"bot:{bot.id}", bot.id
        else:
            scope, scope_key, home_key = "team", f"team:{bot.workspace_id}", f"team-{bot.workspace_id}"
        now = isoformat_utc()
        with self._conn() as conn:
            with conn.transaction():
                row = conn.execute(
                    "SELECT * FROM computers WHERE scope_key = %s",
                    (scope_key,),
                ).fetchone()
                if row is None:
                    computer_id = new_id("cmp")
                    conn.execute(
                        """
                        INSERT INTO computers (
                            id, workspace_id, scope, scope_key, home_key, home_revision,
                            kind, provider_ref, state, control_holder, created_at, updated_at
                        ) VALUES (%s, %s, %s, %s, %s, 'empty', 'docker', NULL, 'stopped', 'none', %s, %s)
                        """,
                        (computer_id, bot.workspace_id, scope, scope_key, home_key, now, now),
                    )
                    row = conn.execute("SELECT * FROM computers WHERE id = %s", (computer_id,)).fetchone()
                conn.execute(
                    "UPDATE bots SET computer_id = %s, updated_at = %s WHERE id = %s",
                    (row["id"], now, bot.id),
                )
        return self._computer_from_row(row)

    def get_computer(self, computer_id: str) -> ComputerRecord | None:
        with self._conn() as conn:
            row = conn.execute("SELECT * FROM computers WHERE id = %s", (computer_id,)).fetchone()
            conn.commit()
        return self._computer_from_row(row) if row else None

    def get_computer_for_bot(self, bot: Bot) -> ComputerRecord:
        return self.ensure_computer(bot)

    def save_computer(self, record: ComputerRecord) -> ComputerRecord:
        now = isoformat_utc()
        with self._conn() as conn:
            row = conn.execute(
                """
                UPDATE computers SET
                    home_revision = %s, kind = %s, provider_ref = %s, state = %s,
                    control_holder = %s, control_lease_id = %s, control_lease_expires_at = %s,
                    control_bot_id = %s, execution_run_id = %s, execution_bot_id = %s,
                    execution_lease_expires_at = %s, sleep_at = %s, updated_at = %s
                WHERE id = %s
                RETURNING *
                """,
                (
                    record.home_revision,
                    record.kind,
                    record.provider_ref,
                    record.state,
                    record.control_holder,
                    record.control_lease_id,
                    record.control_lease_expires_at,
                    record.control_bot_id,
                    record.execution_run_id,
                    record.execution_bot_id,
                    record.execution_lease_expires_at,
                    record.sleep_at,
                    now,
                    record.id,
                ),
            ).fetchone()
            conn.commit()
        if row is None:
            raise RuntimeError("computer missing")
        return self._computer_from_row(row)

    def other_bots_using_computer(self, computer_id: str, except_bot_id: str) -> int:
        with self._conn() as conn:
            row = conn.execute(
                """
                SELECT COUNT(*) AS n
                FROM bots
                WHERE computer_id = %s AND id <> %s
                """,
                (computer_id, except_bot_id),
            ).fetchone()
            conn.commit()
        return int(row["n"]) if row else 0

    def list_orphan_computers(self) -> list[ComputerRecord]:
        with self._conn() as conn:
            rows = conn.execute(
                """
                SELECT c.*
                FROM computers c
                WHERE NOT EXISTS (
                    SELECT 1 FROM bots b WHERE b.computer_id = c.id
                )
                ORDER BY c.updated_at ASC
                """
            ).fetchall()
            conn.commit()
        return [self._computer_from_row(row) for row in rows]

    def delete_computer(self, computer_id: str) -> bool:
        with self._conn() as conn:
            row = conn.execute(
                """
                DELETE FROM computers
                WHERE id = %s
                  AND NOT EXISTS (
                      SELECT 1 FROM bots WHERE bots.computer_id = computers.id
                  )
                RETURNING id
                """,
                (computer_id,),
            ).fetchone()
            conn.commit()
        return row is not None

    def busy_bot_name(self, computer: ComputerRecord, except_bot_id: str) -> str | None:
        holder_id = None
        held = computer.state in {"running", "booting"}
        if computer.scope == "team" and held:
            if computer.execution_bot_id and computer.execution_bot_id != except_bot_id:
                holder_id = computer.execution_bot_id
            elif (
                computer.control_bot_id
                and computer.control_bot_id != except_bot_id
                and computer.control_holder == "user"
            ):
                holder_id = computer.control_bot_id
        if holder_id is None and computer.execution_bot_id and computer.execution_bot_id != except_bot_id:
            if self.has_active_run(computer.execution_bot_id):
                holder_id = computer.execution_bot_id
        if holder_id:
            other = self.get_bot(holder_id)
            return other.name if other else holder_id
        with self._conn() as conn:
            row = conn.execute(
                """
                SELECT b.name
                FROM bots b
                JOIN runs r ON r.bot_id = b.id
                WHERE b.computer_id = %s
                  AND b.id <> %s
                  AND r.status IN (
                    'queued', 'leased', 'running', 'waiting_input', 'waiting_takeover'
                  )
                LIMIT 1
                """,
                (computer.id, except_bot_id),
            ).fetchone()
            conn.commit()
        return str(row["name"]) if row else None

    def due_idle_computer_bots(self) -> list[str]:
        now = isoformat_utc()
        with self._conn() as conn:
            rows = conn.execute(
                """
                SELECT b.id
                FROM computers c
                JOIN bots b ON b.computer_id = c.id
                WHERE c.state = 'running'
                  AND c.sleep_at IS NOT NULL
                  AND c.sleep_at <= %s
                  AND c.control_holder <> 'user'
                  AND NOT EXISTS (
                    SELECT 1
                    FROM bots other
                    JOIN runs r ON r.bot_id = other.id
                    WHERE other.computer_id = c.id
                      AND r.status IN (
                        'queued', 'leased', 'running', 'waiting_input', 'waiting_takeover'
                      )
                  )
                ORDER BY c.sleep_at ASC
                """,
                (now,),
            ).fetchall()
            conn.commit()
        return [row["id"] for row in rows]

    def has_active_run(self, bot_id: str) -> bool:
        with self._conn() as conn:
            row = conn.execute(
                """
                SELECT id FROM runs
                WHERE bot_id = %s
                  AND status IN ('queued', 'leased', 'running', 'waiting_input', 'waiting_takeover')
                LIMIT 1
                """,
                (bot_id,),
            ).fetchone()
            conn.commit()
        return row is not None

    def mark_run_waiting_input(self, run_id: str) -> Run | None:
        now = isoformat_utc()
        with self._conn() as conn:
            row = conn.execute(
                """
                UPDATE runs SET status = 'waiting_input' WHERE id = %s
                RETURNING *
                """,
                (run_id,),
            ).fetchone()
            conn.execute(
                """
                UPDATE bots SET status = 'waiting_input', updated_at = %s
                WHERE id = (SELECT bot_id FROM runs WHERE id = %s)
                """,
                (now, run_id),
            )
            conn.commit()
        return self._run_from_row(row) if row else None

    def mark_run_running(self, run_id: str) -> Run | None:
        now = isoformat_utc()
        with self._conn() as conn:
            row = conn.execute(
                """
                UPDATE runs SET status = 'running' WHERE id = %s AND status = 'waiting_input'
                RETURNING *
                """,
                (run_id,),
            ).fetchone()
            conn.execute(
                """
                UPDATE bots SET status = 'running', updated_at = %s
                WHERE id = (SELECT bot_id FROM runs WHERE id = %s)
                """,
                (now, run_id),
            )
            conn.commit()
        return self._run_from_row(row) if row else None

    def mark_run_waiting_takeover(self, run_id: str) -> Run | None:
        now = isoformat_utc()
        with self._conn() as conn:
            row = conn.execute(
                """
                UPDATE runs SET status = 'waiting_takeover' WHERE id = %s
                RETURNING *
                """,
                (run_id,),
            ).fetchone()
            conn.execute(
                "UPDATE bots SET status = 'idle', updated_at = %s WHERE id = (SELECT bot_id FROM runs WHERE id = %s)",
                (now, run_id),
            )
            conn.commit()
        return self._run_from_row(row) if row else None

    def waiting_takeover_run(self, bot_id: str) -> Run | None:
        with self._conn() as conn:
            row = conn.execute(
                """
                SELECT * FROM runs
                WHERE bot_id = %s AND status = 'waiting_takeover'
                ORDER BY started_at DESC
                LIMIT 1
                """,
                (bot_id,),
            ).fetchone()
            conn.commit()
        return self._run_from_row(row) if row else None

    def _computer_from_row(self, row: dict[str, Any]) -> ComputerRecord:
        return ComputerRecord(
            id=row["id"],
            workspace_id=row["workspace_id"],
            scope=row["scope"],
            scope_key=row["scope_key"],
            home_key=row["home_key"],
            home_revision=row.get("home_revision"),
            kind=row.get("kind") or "docker",
            provider_ref=row.get("provider_ref"),
            state=row.get("state") or "stopped",
            control_holder=row.get("control_holder") or "none",
            control_lease_id=row.get("control_lease_id"),
            control_lease_expires_at=parse_iso(row["control_lease_expires_at"])
            if row.get("control_lease_expires_at")
            else None,
            control_bot_id=row.get("control_bot_id"),
            execution_run_id=row.get("execution_run_id"),
            execution_bot_id=row.get("execution_bot_id"),
            execution_lease_expires_at=parse_iso(row["execution_lease_expires_at"])
            if row.get("execution_lease_expires_at")
            else None,
            sleep_at=parse_iso(row["sleep_at"]) if row.get("sleep_at") else None,
            updated_at=parse_iso(row["updated_at"]),
        )

    def _routine_from_row(self, row: dict[str, Any]) -> Routine:
        return Routine(
            id=row["id"],
            bot_id=row["bot_id"],
            name=row["name"],
            prompt=row["prompt"],
            cron=row["cron"],
            timezone=row["timezone"] or "UTC",
            active=bool(row["active"]),
            notify=bool(row["notify"]),
            last_run_at=parse_iso(row["last_run_at"]) if row["last_run_at"] else None,
            next_run_at=parse_iso(row["next_run_at"]) if row["next_run_at"] else None,
            created_at=parse_iso(row["created_at"]),
        )
