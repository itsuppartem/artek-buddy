from __future__ import annotations

import logging
from typing import Any

from artek_buddy.contracts.domain import (
    Bot,
)
from artek_buddy.contracts.ids import DEFAULT_BOT_COLOR, RunStatus
from artek_buddy.db.shaping import (
    DEFAULT_WORKSPACE_ID,
    isoformat_utc,
    new_id,
    parse_iso,
    pick_color,
)

log = logging.getLogger("artek_buddy")


class BotsMixin:
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

    def fail_orphaned_runs(
        self, error: str = "The host restarted before this turn finished."
    ) -> int:
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

    def _bot_count(self) -> int:
        with self._conn() as conn:
            row = conn.execute("SELECT COUNT(*) AS n FROM bots").fetchone()
            conn.commit()
        return int(row["n"]) if row else 0

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
