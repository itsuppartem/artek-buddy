from __future__ import annotations

import logging
from typing import Any, Literal

from psycopg.errors import UniqueViolation
from psycopg.types.json import Json

from artek_buddy.contracts.domain import (
    Bot,
    Run,
    ThreadMessage,
)
from artek_buddy.contracts.events import MessageRole
from artek_buddy.contracts.ids import RunStatus
from artek_buddy.db.history.commands import CommandPayloadConflict, owner_command_is_needs_setup
from artek_buddy.db.shaping import (
    is_raw_run_failed,
    isoformat_utc,
    new_id,
    parse_iso,
    preview_snippet,
    text_blocks,
)

log = logging.getLogger("artek_buddy")

from artek_buddy.db.history.store import InboxFullError

TurnDisposition = Literal["created", "queued", "replayed", "resumed"]

BUSY_RUN_STATUSES = (
    "queued",
    "leased",
    "running",
    "waiting_input",
    "waiting_takeover",
    "waiting_recovery",
    "unknown",
)
BUSY_RUN_STATUSES_IN = ", ".join(f"'{status}'" for status in BUSY_RUN_STATUSES)


class TurnsMixin:
    def latest_run(self, bot_id: str) -> Run | None:
        with self._conn() as conn:
            row = conn.execute(
                """
                SELECT r.*, w.path AS recovery_path
                FROM runs r
                LEFT JOIN run_waits w ON w.run_id = r.id
                WHERE r.bot_id = %s
                ORDER BY
                  CASE WHEN r.status IN (
                    'queued', 'leased', 'running', 'waiting_input', 'waiting_takeover', 'waiting_recovery', 'unknown'
                  ) THEN 0 ELSE 1 END,
                  r.started_at DESC NULLS LAST,
                  r.id DESC
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
                  AND status IN ("""
                + BUSY_RUN_STATUSES_IN
                + ")",
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
        inbox_text: str | None = None,
        command_id: str | None = None,
        payload_hash: str | None = None,
        parent_command_id: str | None = None,
    ) -> tuple[ThreadMessage, Run, TurnDisposition]:
        """Atomically start a lead turn or queue behind the current lead."""
        message_blocks = blocks or text_blocks(text)
        preview_text = preview or text
        inbox_body = inbox_text if inbox_text is not None else text
        try:
            return self._begin_or_enqueue_turn(
                bot,
                model_provider=model_provider,
                model_id=model_id,
                trigger=trigger,
                reply_to_id=reply_to_id,
                max_inbox=max_inbox,
                message_blocks=message_blocks,
                preview_text=preview_text,
                inbox_body=inbox_body,
                command_id=command_id,
                payload_hash=payload_hash,
                parent_command_id=parent_command_id,
            )
        except UniqueViolation:
            if not command_id:
                raise
            found = self.get_owner_command(bot.id, command_id)
            if found is None:
                raise
            if payload_hash and found.payload_hash != payload_hash:
                raise CommandPayloadConflict from None
            user = self._get_message(found.message_id) if found.message_id else None
            if user is None:
                raise RuntimeError("failed to replay owner command") from None
            if owner_command_is_needs_setup(found.run_id):
                raise RuntimeError("needs_setup owner command is not replayable here") from None
            run = self._get_run(found.run_id)
            if run is None:
                raise RuntimeError("failed to replay owner command") from None
            return self._with_replies([user])[0], run, "replayed"

    def _begin_or_enqueue_turn(
        self,
        bot: Bot,
        *,
        model_provider: str | None,
        model_id: str | None,
        trigger: str,
        reply_to_id: str | None,
        max_inbox: int,
        message_blocks: list[dict[str, Any]],
        preview_text: str,
        inbox_body: str,
        command_id: str | None,
        payload_hash: str | None,
        parent_command_id: str | None,
    ) -> tuple[ThreadMessage, Run, TurnDisposition]:
        resume_setup_message_id: str | None = None
        with self._conn() as conn:
            with conn.transaction():
                locked = conn.execute(
                    "SELECT id FROM bots WHERE id = %s FOR UPDATE",
                    (bot.id,),
                ).fetchone()
                if locked is None:
                    raise RuntimeError("bot not found")
                if command_id:
                    existing = conn.execute(
                        """
                        SELECT command_id, bot_id, payload_hash, run_id, message_id
                        FROM owner_commands
                        WHERE command_id = %s
                        FOR UPDATE
                        """,
                        (command_id,),
                    ).fetchone()
                    if existing is not None:
                        if existing["bot_id"] != bot.id or (
                            payload_hash and existing["payload_hash"] != payload_hash
                        ):
                            raise CommandPayloadConflict
                        user = self._get_message(str(existing["message_id"]))
                        if user is None:
                            raise RuntimeError("failed to replay owner command")
                        if owner_command_is_needs_setup(str(existing["run_id"])):
                            resume_setup_message_id = str(existing["message_id"])
                        else:
                            run = self._get_run(str(existing["run_id"]))
                            if run is None:
                                raise RuntimeError("failed to replay owner command")
                            return self._with_replies([user])[0], run, "replayed"
                active = conn.execute(
                    """
                    SELECT * FROM runs
                    WHERE bot_id = %s
                      AND status IN ('queued', 'leased', 'running', 'waiting_input', 'waiting_takeover', 'waiting_recovery', 'unknown')
                    ORDER BY started_at DESC
                    LIMIT 1
                    FOR UPDATE
                    """,
                    (bot.id,),
                ).fetchone()
                if active is not None and active["status"] in {
                    "waiting_takeover",
                    "waiting_recovery",
                    "unknown",
                }:
                    conn.execute(
                        """
                        UPDATE runs
                        SET status = %s, error = %s, completed_at = %s
                        WHERE id = %s
                        """,
                        (
                            RunStatus.cancelled.value,
                            (
                                "The owner started a new attempt."
                                if active["status"] in {"unknown", "waiting_recovery"}
                                else "Stopped."
                            ),
                            isoformat_utc(),
                            active["id"],
                        ),
                    )
                    active = None
                now = isoformat_utc()
                if resume_setup_message_id is not None:
                    msg_id = resume_setup_message_id
                    user = self._get_message(msg_id)
                    if user is None:
                        raise RuntimeError("failed to resume needs_setup owner command")
                    seq = user.seq
                else:
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
                    if resume_setup_message_id is None:
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
                        INSERT INTO turn_inbox (
                            id, bot_id, message_id, text, reply_to_id, created_at, kind
                        )
                        VALUES (%s, %s, %s, %s, %s, %s, 'owner')
                        """,
                        (new_id("inb"), bot.id, msg_id, inbox_body, reply_to_id, now),
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
                    if resume_setup_message_id is None:
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
                    else:
                        conn.execute(
                            """
                            UPDATE messages
                            SET run_id = %s
                            WHERE id = %s AND thread_id = %s
                            """,
                            (run_id, msg_id, bot.thread_id),
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
                if resume_setup_message_id is None:
                    self._record_message_created(
                        conn,
                        bot_id=bot.id,
                        thread_id=bot.thread_id,
                        message_id=msg_id,
                        role="user",
                        seq=seq,
                        run_id=run_id,
                        blocks=message_blocks,
                    )
                if command_id:
                    if resume_setup_message_id is not None:
                        conn.execute(
                            """
                            UPDATE owner_commands
                            SET run_id = %s
                            WHERE command_id = %s AND bot_id = %s
                            """,
                            (run_id, command_id, bot.id),
                        )
                    else:
                        conn.execute(
                            """
                            INSERT INTO owner_commands (
                                command_id, bot_id, payload_hash, run_id, message_id,
                                parent_command_id, created_at
                            )
                            VALUES (%s, %s, %s, %s, %s, %s, %s)
                            """,
                            (
                                command_id,
                                bot.id,
                                payload_hash or "",
                                run_id,
                                msg_id,
                                parent_command_id,
                                now,
                            ),
                        )
                if not queued_turn:
                    conn.execute(
                        """
                        INSERT INTO turn_dispatches (run_id, bot_id, state, created_at)
                        VALUES (%s, %s, 'pending', %s)
                        """,
                        (run_id, bot.id, now),
                    )
        user = self._get_message(msg_id)
        run = self._get_run(run_id)
        if user is None or run is None:
            raise RuntimeError("failed to persist turn")
        if not queued_turn:
            self.bind_run_fast(run.id)
        if resume_setup_message_id is not None and not queued_turn:
            disposition: TurnDisposition = "resumed"
        else:
            disposition = "queued" if queued_turn else "created"
        return self._with_replies([user])[0], run, disposition

    def claim_turn_dispatch(self, run_id: str) -> bool:
        """Claim pending lead dispatch once. Replay and a second POST lose."""
        if not run_id:
            return False
        now = isoformat_utc()
        with self._conn() as conn:
            row = conn.execute(
                """
                UPDATE turn_dispatches
                SET state = 'claimed', claimed_at = %s
                WHERE run_id = %s AND state = 'pending'
                RETURNING run_id
                """,
                (now, run_id),
            ).fetchone()
            conn.commit()
        return row is not None

    def record_worker_stop(
        self,
        bot: Bot,
        *,
        model_provider: str | None = None,
        model_id: str | None = None,
    ) -> Run:
        now = isoformat_utc()
        run_id = new_id("run")
        task_id = new_id("tsk")
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO runs (
                    id, bot_id, thread_id, task_id, status, trigger,
                    model_provider, model_id, error, result, started_at, completed_at
                ) VALUES (
                    %s, %s, %s, %s, %s, 'user',
                    %s, %s, %s, NULL, %s, %s
                )
                """,
                (
                    run_id,
                    bot.id,
                    bot.thread_id,
                    task_id,
                    RunStatus.cancelled.value,
                    model_provider,
                    model_id,
                    "Stopped.",
                    now,
                    now,
                ),
            )
            conn.execute(
                "UPDATE bots SET status = %s, updated_at = %s WHERE id = %s",
                ("idle", now, bot.id),
            )
            conn.commit()
        run = self._get_run(run_id)
        if run is None:
            raise RuntimeError("failed to persist worker stop")
        return run

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
                self._record_message_created(
                    conn,
                    bot_id=bot.id,
                    thread_id=bot.thread_id,
                    message_id=msg_id,
                    role="user",
                    seq=seq,
                    run_id=run_id,
                    blocks=blocks,
                )
        user = self._get_message(msg_id)
        run = self._get_run(run_id)
        if user is None or run is None:
            raise RuntimeError("failed to persist turn start")
        self.bind_run_fast(run.id)
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
                recovered = conn.execute(
                    "SELECT recovered_at FROM run_waits WHERE run_id = %s",
                    (run.id,),
                ).fetchone()
                already_status = already["status"] if already else None
                skip_late = bool(
                    recovered
                    and recovered["recovered_at"] is not None
                    and status != RunStatus.cancelled.value
                ) or (
                    already_status == RunStatus.cancelled.value
                    and status != RunStatus.cancelled.value
                )
                skip_dup_unknown = (
                    already_status == RunStatus.unknown.value and status == RunStatus.unknown.value
                )
                if not skip_late and not skip_dup_unknown:
                    now = isoformat_utc()
                    body = (text or "").strip() if text else ""
                    err = (error or "").strip()
                    if body and (body == err or is_raw_run_failed(body)):
                        body = ""
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
                        self._record_message_created(
                            conn,
                            bot_id=bot.id,
                            thread_id=bot.thread_id,
                            message_id=msg_id,
                            role="bot",
                            seq=seq,
                            run_id=run.id,
                            blocks=blocks,
                        )
                    conn.execute(
                        """
                        UPDATE runs
                        SET status = %s, error = %s, result = %s, completed_at = %s
                        WHERE id = %s
                        """,
                        (
                            status,
                            error,
                            text or None,
                            None if status == RunStatus.unknown.value else now,
                            run.id,
                        ),
                    )
                    still = conn.execute(
                        """
                        SELECT 1 FROM runs
                        WHERE bot_id = %s
                          AND id <> %s
                          AND status IN (
                            'queued', 'leased', 'running', 'waiting_input', 'waiting_takeover', 'waiting_recovery', 'unknown'
                          )
                        LIMIT 1
                        """,
                        (bot.id, run.id),
                    ).fetchone()
                    if still:
                        bot_status = "running"
                    elif status in {RunStatus.completed.value, RunStatus.cancelled.value}:
                        bot_status = "idle"
                    elif status == RunStatus.unknown.value:
                        bot_status = "running"
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
        self.bind_run_fast(run.id)
        return run

    def _get_run(self, run_id: str) -> Run | None:
        with self._conn() as conn:
            row = conn.execute(
                """
                SELECT r.*, w.path AS recovery_path
                FROM runs r
                LEFT JOIN run_waits w ON w.run_id = r.id
                WHERE r.id = %s
                """,
                (run_id,),
            ).fetchone()
            conn.commit()
        return self._run_from_row(row) if row else None

    def get_run(self, run_id: str) -> Run | None:
        return self._get_run(run_id)

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
            recovery_path=row.get("recovery_path"),
        )

    def has_active_run(self, bot_id: str) -> bool:
        with self._conn() as conn:
            row = conn.execute(
                """
                SELECT id FROM runs
                WHERE bot_id = %s
                  AND status IN ('queued', 'leased', 'running', 'waiting_input', 'waiting_takeover', 'waiting_recovery', 'unknown')
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
                UPDATE runs SET status = 'waiting_input'
                WHERE id = %s
                  AND status IN ('queued', 'leased', 'running')
                RETURNING *
                """,
                (run_id,),
            ).fetchone()
            if row is None:
                conn.commit()
                return None
            conn.execute(
                """
                UPDATE bots SET status = 'waiting_input', updated_at = %s
                WHERE id = %s
                """,
                (now, row["bot_id"]),
            )
            conn.commit()
        return self._run_from_row(row)

    def mark_run_running(self, run_id: str) -> Run | None:
        now = isoformat_utc()
        with self._conn() as conn:
            row = conn.execute(
                """
                UPDATE runs SET status = 'running'
                WHERE id = %s AND status IN ('waiting_input', 'waiting_takeover')
                RETURNING *
                """,
                (run_id,),
            ).fetchone()
            if row is None:
                conn.commit()
                return None
            conn.execute(
                """
                UPDATE bots SET status = 'running', updated_at = %s
                WHERE id = %s
                """,
                (now, row["bot_id"]),
            )
            conn.commit()
        return self._run_from_row(row)

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
        parked = self._run_from_row(row) if row else None
        if parked is not None:
            bind = getattr(self, "bind_run_wait", None)
            if callable(bind):
                bind(
                    run_id,
                    parked.bot_id,
                    kind="takeover",
                    path="new_attempt",
                    effect="intended",
                )
        return parked

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
