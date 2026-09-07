from __future__ import annotations

import base64
import html
from typing import Any

from psycopg.errors import QueryCanceled

from artek_buddy.contracts.domain import Principal
from artek_buddy.contracts.search import SearchHit, SearchPage
from artek_buddy.db.shaping import (
    DEFAULT_WORKSPACE_ID,
    isoformat_utc,
    new_id,
)
from artek_buddy.search_policy import (
    SEARCH_DOCUMENT_KINDS,
    SEARCH_HEADLINE_OPTIONS,
    SEARCH_REBUILD_BATCH,
    SEARCH_REBUILD_IDEMPOTENCY,
    authorized_search_resource_ids,
    cap_search_limit,
    index_body,
    normalize_search_query,
    parse_search_kinds,
    searchable_message_text,
)

_REBUILD_PHASES = ("bots", "messages", "memory", "artifacts")


class SearchTimeoutError(Exception):
    """Postgres cancelled the ranked query (statement_timeout)."""


class SearchMixin:
    def ensure_search_index(self) -> None:
        self.enqueue_job(
            job_type="search.rebuild",
            payload={"version": 1, "phase": "bots", "after_id": ""},
            resource_id="search",
            idempotency_key=SEARCH_REBUILD_IDEMPOTENCY,
            max_attempts=8,
        )

    def authorized_search_resource_ids(self, principal: Principal) -> list[str]:
        bot_ids = [bot.id for bot in self.list_bots()]
        bot_ids.extend(bot.id for bot in self.list_archived_bots())
        return authorized_search_resource_ids(principal, bot_ids, DEFAULT_WORKSPACE_ID)

    def _index_search_message_tx(
        self,
        conn: Any,
        *,
        bot_id: str,
        message_id: str,
        blocks: list[Any] | None,
    ) -> None:
        body = index_body(searchable_message_text(blocks))
        if not body:
            return
        self._upsert_search_document_tx(
            conn,
            document_kind="message",
            resource_id=bot_id,
            source_id=message_id,
            title="",
            body=body,
        )

    def _upsert_search_document_tx(
        self,
        conn: Any,
        *,
        document_kind: str,
        resource_id: str,
        source_id: str,
        title: str,
        body: str,
        resource_kind: str = "bot",
    ) -> None:
        now = isoformat_utc()
        conn.execute(
            """
            INSERT INTO search_documents (
                id, document_kind, resource_kind, resource_id, source_id,
                title, body, created_at, updated_at, deleted_at
            ) VALUES (
                %s, %s, %s, %s, %s,
                %s, %s, %s, %s, NULL
            )
            ON CONFLICT (document_kind, source_id) DO UPDATE SET
                resource_kind = EXCLUDED.resource_kind,
                resource_id = EXCLUDED.resource_id,
                title = EXCLUDED.title,
                body = EXCLUDED.body,
                updated_at = EXCLUDED.updated_at,
                deleted_at = NULL
            """,
            (
                new_id("sdoc"),
                document_kind,
                resource_kind,
                resource_id,
                source_id,
                title or "",
                index_body(body),
                now,
                now,
            ),
        )

    def upsert_search_document(
        self,
        *,
        document_kind: str,
        resource_id: str,
        source_id: str,
        title: str,
        body: str,
        resource_kind: str = "bot",
    ) -> None:
        with self._conn() as conn:
            self._upsert_search_document_tx(
                conn,
                document_kind=document_kind,
                resource_id=resource_id,
                source_id=source_id,
                title=title,
                body=body,
                resource_kind=resource_kind,
            )
            conn.commit()

    def _tombstone_search_source_tx(self, conn: Any, document_kind: str, source_id: str) -> None:
        conn.execute(
            """
            UPDATE search_documents
            SET deleted_at = COALESCE(deleted_at, now()), updated_at = now()
            WHERE document_kind = %s AND source_id = %s AND deleted_at IS NULL
            """,
            (document_kind, source_id),
        )

    def _tombstone_search_resource_tx(self, conn: Any, resource_id: str) -> None:
        conn.execute(
            """
            UPDATE search_documents
            SET deleted_at = COALESCE(deleted_at, now()), updated_at = now()
            WHERE resource_id = %s AND deleted_at IS NULL
            """,
            (resource_id,),
        )

    def search_documents(
        self,
        principal: Principal,
        *,
        query: str,
        kinds: str | None = None,
        cursor: str | None = None,
        limit: int | None = None,
    ) -> SearchPage:
        needle = normalize_search_query(query)
        wanted = parse_search_kinds(kinds)
        page_size = cap_search_limit(limit)
        if not needle or not wanted:
            return SearchPage()
        resource_ids = self.authorized_search_resource_ids(principal)
        if not resource_ids:
            return SearchPage()
        after_rank, after_id = _decode_search_cursor(cursor)
        fetch = page_size + 1
        try:
            with self._conn() as conn:
                with conn.transaction():
                    conn.execute("SET LOCAL statement_timeout = '800ms'")
                    rows = conn.execute(
                        """
                        WITH q AS (
                            SELECT plainto_tsquery('simple', %s) AS tsq
                        )
                        SELECT
                            d.id,
                            d.document_kind,
                            d.resource_id,
                            d.source_id,
                            d.title,
                            ts_rank(d.search_vector, q.tsq) AS rank,
                            ts_headline(
                                'simple',
                                left(d.body, 2000),
                                q.tsq,
                                %s
                            ) AS snippet
                        FROM search_documents d, q
                        WHERE d.deleted_at IS NULL
                          AND d.resource_id = ANY(%s)
                          AND d.document_kind = ANY(%s)
                          AND q.tsq <> ''::tsquery
                          AND d.search_vector @@ q.tsq
                          AND (
                            %s::double precision IS NULL
                            OR ts_rank(d.search_vector, q.tsq) < %s
                            OR (
                                ts_rank(d.search_vector, q.tsq) = %s
                                AND d.id < %s
                            )
                          )
                        ORDER BY ts_rank(d.search_vector, q.tsq) DESC, d.id DESC
                        LIMIT %s
                        """,
                        (
                            needle,
                            SEARCH_HEADLINE_OPTIONS,
                            resource_ids,
                            wanted,
                            after_rank,
                            after_rank,
                            after_rank,
                            after_id or "",
                            fetch,
                        ),
                    ).fetchall()
        except QueryCanceled as err:
            raise SearchTimeoutError("search timed out") from err
        hits: list[SearchHit] = []
        last_rank = 0.0
        for row in rows[:page_size]:
            kind = str(row["document_kind"])
            if kind not in SEARCH_DOCUMENT_KINDS:
                continue
            last_rank = float(row["rank"] or 0)
            hits.append(
                SearchHit(
                    id=str(row["id"]),
                    document_kind=kind,  # type: ignore[arg-type]
                    resource_id=str(row["resource_id"]),
                    source_id=str(row["source_id"]),
                    title=str(row["title"] or ""),
                    snippet=_safe_snippet(row.get("snippet") or ""),
                )
            )
        has_more = len(rows) > page_size
        next_cursor = None
        if has_more and hits:
            next_cursor = _encode_search_cursor(last_rank, hits[-1].id)
        return SearchPage(hits=hits, has_more=has_more, next_cursor=next_cursor)

    def rebuild_search_chunk(
        self,
        payload: dict[str, Any] | None = None,
        *,
        batch: int = SEARCH_REBUILD_BATCH,
    ) -> tuple[dict[str, Any], bool]:
        state = dict(payload or {})
        phase = str(state.get("phase") or "bots")
        after_id = str(state.get("after_id") or "")
        if phase not in _REBUILD_PHASES:
            return {"version": 1, "phase": "done", "after_id": ""}, True
        batch = max(1, min(int(batch), 200))
        with self._conn() as conn:
            with conn.transaction():
                processed, last_id = self._rebuild_phase_chunk(conn, phase, after_id, batch)
        if processed >= batch:
            return {"version": 1, "phase": phase, "after_id": last_id}, False
        idx = _REBUILD_PHASES.index(phase)
        if idx + 1 >= len(_REBUILD_PHASES):
            return {"version": 1, "phase": "done", "after_id": ""}, True
        return {"version": 1, "phase": _REBUILD_PHASES[idx + 1], "after_id": ""}, False

    def _rebuild_phase_chunk(
        self, conn: Any, phase: str, after_id: str, batch: int
    ) -> tuple[int, str]:
        if phase == "bots":
            rows = conn.execute(
                """
                SELECT id, name, title FROM bots
                WHERE id > %s ORDER BY id LIMIT %s
                """,
                (after_id, batch),
            ).fetchall()
            for row in rows:
                self._upsert_search_document_tx(
                    conn,
                    document_kind="bot",
                    resource_id=str(row["id"]),
                    source_id=str(row["id"]),
                    title=str(row["name"] or ""),
                    body=str(row["title"] or ""),
                )
        elif phase == "messages":
            rows = conn.execute(
                """
                SELECT m.id, b.id AS bot_id, m.blocks
                FROM messages m
                JOIN threads t ON t.id = m.thread_id
                JOIN bots b ON b.id = t.bot_id
                WHERE m.id > %s ORDER BY m.id LIMIT %s
                """,
                (after_id, batch),
            ).fetchall()
            for row in rows:
                blocks = row["blocks"]
                if isinstance(blocks, str):
                    continue
                body = searchable_message_text(blocks)
                if not body:
                    continue
                self._upsert_search_document_tx(
                    conn,
                    document_kind="message",
                    resource_id=str(row["bot_id"]),
                    source_id=str(row["id"]),
                    title="",
                    body=body,
                )
        elif phase == "memory":
            rows = conn.execute(
                """
                SELECT id, workspace_id, bot_id, path, content
                FROM memory_documents
                WHERE id > %s ORDER BY id LIMIT %s
                """,
                (after_id, batch),
            ).fetchall()
            for row in rows:
                resource_id = str(row["bot_id"] or row["workspace_id"] or DEFAULT_WORKSPACE_ID)
                self._upsert_search_document_tx(
                    conn,
                    document_kind="memory",
                    resource_id=resource_id,
                    source_id=str(row["id"]),
                    title=str(row["path"] or ""),
                    body=str(row["content"] or ""),
                )
        else:
            rows = conn.execute(
                """
                SELECT id, bot_id, name, mime_type FROM artifacts
                WHERE id > %s ORDER BY id LIMIT %s
                """,
                (after_id, batch),
            ).fetchall()
            for row in rows:
                self._upsert_search_document_tx(
                    conn,
                    document_kind="artifact",
                    resource_id=str(row["bot_id"]),
                    source_id=str(row["id"]),
                    title=str(row["name"] or ""),
                    body=str(row["mime_type"] or ""),
                )
        last_id = str(rows[-1]["id"]) if rows else after_id
        return len(rows), last_id


def _safe_snippet(raw: str) -> str:
    text = " ".join(html.escape(str(raw), quote=True).split())
    return text[:280]


def _encode_search_cursor(rank: float, doc_id: str) -> str:
    raw = f"{rank:.12f}\t{doc_id}".encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _decode_search_cursor(cursor: str | None) -> tuple[float | None, str | None]:
    if not cursor or not str(cursor).strip():
        return None, None
    padded = str(cursor).strip() + "=" * ((4 - len(str(cursor).strip()) % 4) % 4)
    try:
        raw = base64.urlsafe_b64decode(padded.encode()).decode()
        rank_s, doc_id = raw.split("\t", 1)
        return float(rank_s), doc_id
    except (ValueError, TypeError):
        return None, None
