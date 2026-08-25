from __future__ import annotations

from typing import Any

from artek_buddy.db.shaping import isoformat_utc, new_id


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

    def take_undelivered_ask_for_run(
        self, to_run_id: str, reply_text: str
    ) -> dict[str, Any] | None:
        with self._conn() as conn:
            row = conn.execute(
                """
                UPDATE bot_asks
                SET delivered_at = %s, reply_text = %s
                WHERE id = (
                    SELECT id FROM bot_asks
                    WHERE to_run_id = %s AND delivered_at IS NULL
                    LIMIT 1
                )
                RETURNING *
                """,
                (isoformat_utc(), reply_text, to_run_id),
            ).fetchone()
            conn.commit()
        return dict(row) if row else None
