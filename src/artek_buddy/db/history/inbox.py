from __future__ import annotations

import logging

from artek_buddy.contracts.domain import (
    Bot,
    Run,
)
from artek_buddy.contracts.ids import RunStatus
from artek_buddy.db.shaping import (
    isoformat_utc,
    new_id,
)

log = logging.getLogger("artek_buddy")


class InboxMixin:
    def enqueue_inbox(
        self,
        bot_id: str,
        message_id: str | None,
        text: str,
        reply_to_id: str | None = None,
        *,
        kind: str = "owner",
    ) -> None:
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO turn_inbox (id, bot_id, message_id, text, reply_to_id, created_at, kind)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                """,
                (new_id("inb"), bot_id, message_id, text, reply_to_id, isoformat_utc(), kind),
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

    def drain_inbox(
        self,
        bot_id: str,
        *,
        kind: str | None = "owner",
    ) -> list[dict[str, str | None]]:
        with self._conn() as conn:
            with conn.transaction():
                if kind is None:
                    rows = conn.execute(
                        """
                        SELECT id, message_id, text, reply_to_id, kind
                        FROM turn_inbox
                        WHERE bot_id = %s
                        ORDER BY created_at ASC
                        FOR UPDATE
                        """,
                        (bot_id,),
                    ).fetchall()
                    if rows:
                        conn.execute("DELETE FROM turn_inbox WHERE bot_id = %s", (bot_id,))
                else:
                    rows = conn.execute(
                        """
                        SELECT id, message_id, text, reply_to_id, kind
                        FROM turn_inbox
                        WHERE bot_id = %s AND kind = %s
                        ORDER BY created_at ASC
                        FOR UPDATE
                        """,
                        (bot_id, kind),
                    ).fetchall()
                    if rows:
                        conn.execute(
                            "DELETE FROM turn_inbox WHERE bot_id = %s AND kind = %s",
                            (bot_id, kind),
                        )
        return [
            {
                "message_id": row["message_id"],
                "text": row["text"],
                "reply_to_id": row["reply_to_id"],
                "kind": row["kind"] if "kind" in row else "owner",
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
                    SELECT id, message_id, text, reply_to_id, kind
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
                    "kind": row["kind"] if "kind" in row else "owner",
                }
                for row in rows
            ],
        )
