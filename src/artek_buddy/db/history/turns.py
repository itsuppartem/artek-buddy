from __future__ import annotations

import logging
from typing import Any

from psycopg.types.json import Json

from artek_buddy.contracts.domain import (
    Bot,
    Run,
    ThreadMessage,
)
from artek_buddy.contracts.events import MessageRole
from artek_buddy.contracts.ids import RunStatus
from artek_buddy.db.shaping import (
    isoformat_utc,
    new_id,
    parse_iso,
    preview_snippet,
    text_blocks,
)

log = logging.getLogger("artek_buddy")

from artek_buddy.db.history.store import InboxFullError


class TurnsMixin:
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
                            (
                                msg_id,
                                bot.thread_id,
                                seq,
                                MessageRole.bot.value,
                                Json(blocks),
                                run.id,
                                now,
                            ),
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

    def _get_run(self, run_id: str) -> Run | None:
        with self._conn() as conn:
            row = conn.execute("SELECT * FROM runs WHERE id = %s", (run_id,)).fetchone()
            conn.commit()
        return self._run_from_row(row) if row else None

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
                UPDATE runs SET status = 'running' WHERE id = %s AND status IN ('waiting_input', 'waiting_takeover')
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
                """
                UPDATE bots SET status = 'waiting_takeover', updated_at = %s
                WHERE id = (SELECT bot_id FROM runs WHERE id = %s)
                """,
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
