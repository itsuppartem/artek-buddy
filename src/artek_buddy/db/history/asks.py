from __future__ import annotations

from typing import Any

from psycopg.types.json import Json

from artek_buddy.contracts.domain import Bot, Run, ThreadMessage
from artek_buddy.contracts.events import MessageRole
from artek_buddy.contracts.ids import RunStatus
from artek_buddy.db.shaping import isoformat_utc, new_id, preview_snippet


class AsksMixin:
    def create_bot_ask(
        self,
        *,
        from_bot_id: str,
        to_bot_id: str,
        question: str,
        from_run_id: str | None = None,
    ) -> str:
        ask_id = new_id("ask")
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO bot_asks (
                    id, from_bot_id, to_bot_id, from_run_id, to_run_id,
                    question, reply_text, delivered_at, created_at
                ) VALUES (
                    %s, %s, %s, %s, NULL,
                    %s, NULL, NULL, %s
                )
                """,
                (ask_id, from_bot_id, to_bot_id, from_run_id, question, isoformat_utc()),
            )
            conn.commit()
        return ask_id

    def bind_pending_ask_run(self, to_bot_id: str, run_id: str) -> str | None:
        with self._conn() as conn:
            row = conn.execute(
                """
                UPDATE bot_asks
                SET to_run_id = %s
                WHERE id = (
                    SELECT id FROM bot_asks
                    WHERE to_bot_id = %s
                      AND delivered_at IS NULL
                      AND to_run_id IS NULL
                    ORDER BY created_at ASC
                    LIMIT 1
                )
                RETURNING id
                """,
                (run_id, to_bot_id),
            ).fetchone()
            conn.commit()
        return str(row["id"]) if row else None

    def peek_undelivered_ask_for_run(self, to_run_id: str) -> dict[str, Any] | None:
        with self._conn() as conn:
            row = conn.execute(
                """
                SELECT * FROM bot_asks
                WHERE to_run_id = %s AND delivered_at IS NULL
                LIMIT 1
                """,
                (to_run_id,),
            ).fetchone()
            conn.commit()
        return dict(row) if row else None

    def get_bot_ask_for_to_run(self, to_run_id: str) -> dict[str, Any] | None:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM bot_asks WHERE to_run_id = %s LIMIT 1",
                (to_run_id,),
            ).fetchone()
            conn.commit()
        return dict(row) if row else None

    def deliver_bot_ask_follow_up(
        self,
        *,
        to_run_id: str,
        reply_text: str,
        source: Bot,
        ready_blocks: list[dict[str, Any]],
        prompt: str,
        model_provider: str | None,
        model_id: str | None,
    ) -> tuple[dict[str, Any], ThreadMessage, Run | None] | None:
        """Mark the ask delivered only with an inbox item or a follow-up run."""
        msg_id = new_id("msg")
        follow_id: str | None = None
        ask_row: dict[str, Any] | None = None
        now = isoformat_utc()
        with self._conn() as conn:
            with conn.transaction():
                locked_ask = conn.execute(
                    """
                    SELECT id FROM bot_asks
                    WHERE to_run_id = %s AND delivered_at IS NULL
                    LIMIT 1
                    FOR UPDATE
                    """,
                    (to_run_id,),
                ).fetchone()
                if locked_ask is None:
                    return None
                bot_row = conn.execute(
                    "SELECT id FROM bots WHERE id = %s FOR UPDATE",
                    (source.id,),
                ).fetchone()
                if bot_row is None:
                    return None
                row = conn.execute(
                    """
                    UPDATE bot_asks
                    SET delivered_at = %s, reply_text = %s
                    WHERE id = %s
                    RETURNING *
                    """,
                    (now, reply_text, locked_ask["id"]),
                ).fetchone()
                if row is None:
                    return None
                ask_row = dict(row)
                active = conn.execute(
                    """
                    SELECT COUNT(*) AS n FROM runs
                    WHERE bot_id = %s
                      AND status IN (
                        'queued', 'leased', 'running', 'waiting_input', 'waiting_takeover'
                      )
                    """,
                    (source.id,),
                ).fetchone()
                busy = int(active["n"]) > 0 if active else False
                seq = self._lock_next_seq(conn, source.thread_id)
                conn.execute(
                    """
                    INSERT INTO messages (
                        id, thread_id, seq, role, blocks, run_id, reply_to_id, created_at
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        msg_id,
                        source.thread_id,
                        seq,
                        MessageRole.bot.value,
                        Json(ready_blocks),
                        str(ask_row.get("from_run_id") or "") or None,
                        None,
                        now,
                    ),
                )
                excerpt = ""
                for block in ready_blocks:
                    if isinstance(block, dict) and block.get("text"):
                        excerpt = str(block["text"])
                        break
                if excerpt:
                    conn.execute(
                        "UPDATE bots SET preview = %s, unread = TRUE, updated_at = %s WHERE id = %s",
                        (preview_snippet(excerpt), now, source.id),
                    )
                if busy:
                    conn.execute(
                        """
                        INSERT INTO turn_inbox (
                            id, bot_id, message_id, text, reply_to_id, created_at, kind
                        )
                        VALUES (%s, %s, %s, %s, NULL, %s, 'owner')
                        """,
                        (new_id("inb"), source.id, msg_id, prompt, now),
                    )
                else:
                    follow_id = new_id("run")
                    task_id = new_id("tsk")
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
                            follow_id,
                            source.id,
                            source.thread_id,
                            task_id,
                            RunStatus.running.value,
                            "follow_up",
                            model_provider,
                            model_id,
                            now,
                        ),
                    )
                    conn.execute(
                        "UPDATE bots SET status = %s, updated_at = %s WHERE id = %s",
                        ("running", now, source.id),
                    )
        if ask_row is None:
            return None
        message = self._get_message(msg_id)
        if message is None:
            raise RuntimeError("failed to persist ask reply card")
        ready = self._with_replies([message])[0]
        follow = self._get_run(follow_id) if follow_id else None
        return ask_row, ready, follow
