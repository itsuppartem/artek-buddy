from __future__ import annotations

import logging
from typing import Any

from psycopg.types.json import Json

from artek_buddy.contracts.domain import (
    Artifact,
    Bot,
    ThreadMessage,
    ThreadMessagePage,
)
from artek_buddy.contracts.events import MessageReplyRef, MessageRole
from artek_buddy.db.shaping import (
    DEFAULT_PAGE_SIZE,
    answer_ask_blocks,
    blocks_text,
    isoformat_utc,
    new_id,
    next_seq,
    older_cursor,
    parse_iso,
    preview_snippet,
    text_blocks,
)

log = logging.getLogger("artek_buddy")


class MessagesMixin:
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

    def answer_message_ask(
        self,
        message_id: str,
        answer: str,
        *,
        include_consent: bool = False,
    ) -> ThreadMessage | None:
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
                include_consent=include_consent,
            )
            if not changed:
                conn.commit()
                return None
            conn.execute(
                "UPDATE messages SET blocks = %s WHERE id = %s",
                (Json(next_blocks), message_id),
            )
            conn.commit()
        return self._get_message(message_id)

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

    def _get_message(self, message_id: str) -> ThreadMessage | None:
        with self._conn() as conn:
            row = conn.execute("SELECT * FROM messages WHERE id = %s", (message_id,)).fetchone()
            conn.commit()
        return self._message_from_row(row) if row else None

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
