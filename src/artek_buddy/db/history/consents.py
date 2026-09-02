from __future__ import annotations

import logging
from typing import Any

from psycopg.errors import UniqueViolation

from artek_buddy.db.shaping import (
    DEFAULT_WORKSPACE_ID,
    isoformat_utc,
    new_id,
)

log = logging.getLogger("artek_buddy")


class ConsentsMixin:
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
        parent_run_id: str | None = None,
        thread_id: str | None = None,
        message_id: str | None = None,
        workspace_id: str = DEFAULT_WORKSPACE_ID,
        job_status: str | None = None,
    ) -> None:
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO consent_requests (
                    id, workspace_id, bot_id, run_id, parent_run_id, thread_id, message_id,
                    action_class, scope_key, summary, status, job_status, created_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'pending', %s, %s)
                """,
                (
                    request_id,
                    workspace_id,
                    bot_id,
                    run_id,
                    parent_run_id,
                    thread_id,
                    message_id,
                    action_class,
                    scope_key,
                    summary,
                    job_status,
                    isoformat_utc(),
                ),
            )
            conn.commit()

    def get_consent_request(self, request_id: str) -> Any:
        from artek_buddy.consent import ConsentRequest

        with self._conn() as conn:
            row = conn.execute(
                """
                SELECT id, bot_id, action_class, scope_key, summary, status, run_id, parent_run_id,
                       message_id, job_status
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
            parent_run_id=row["parent_run_id"],
            message_id=row["message_id"],
            job_status=row["job_status"],
        )

    def pending_auto_consent_id(self, bot_id: str, run_id: str | None) -> str | None:
        pending = self.pending_auto_consent_ids(bot_id, run_id)
        return pending[-1] if pending else None

    def pending_auto_consent_ids(self, bot_id: str, run_ids: str | list[str] | None) -> list[str]:
        if isinstance(run_ids, str):
            ids = [run_ids] if run_ids else []
        else:
            ids = [item for item in (run_ids or []) if item]
        if not ids:
            return []
        with self._conn() as conn:
            rows = conn.execute(
                """
                SELECT id FROM consent_requests
                WHERE bot_id = %s
                  AND status = 'pending'
                  AND job_status = 'queued'
                  AND message_id IS NULL
                  AND (run_id = ANY(%s) OR parent_run_id = ANY(%s))
                ORDER BY created_at, id
                """,
                (bot_id, ids, ids),
            ).fetchall()
            conn.commit()
        return [str(row["id"]) for row in rows]

    def owner_job_ids_for_runs(self, run_ids: list[str]) -> list[str]:
        ids = [item for item in run_ids if item]
        if not ids:
            return []
        with self._conn() as conn:
            rows = conn.execute(
                """
                SELECT id FROM consent_requests
                WHERE run_id = ANY(%s)
                  AND job_status IN ('queued', 'acknowledged')
                """,
                (ids,),
            ).fetchall()
            conn.commit()
        return [str(row["id"]) for row in rows]

    def acknowledge_consent_job(self, request_id: str) -> bool:
        with self._conn() as conn:
            row = conn.execute(
                """
                UPDATE consent_requests
                SET job_status = 'acknowledged', acknowledged_at = %s
                WHERE id = %s AND job_status = 'queued'
                RETURNING id
                """,
                (isoformat_utc(), request_id),
            ).fetchone()
            conn.commit()
        return row is not None

    def finish_consent_job(self, request_id: str, job_status: str) -> bool:
        if job_status not in {"completed", "failed", "timed_out"}:
            raise ValueError("invalid terminal consent job status")
        with self._conn() as conn:
            row = conn.execute(
                """
                UPDATE consent_requests
                SET job_status = %s, completed_at = %s
                WHERE id = %s AND job_status IN ('queued', 'acknowledged')
                RETURNING id
                """,
                (job_status, isoformat_utc(), request_id),
            ).fetchone()
            conn.commit()
        return row is not None

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
                RETURNING id, bot_id, action_class, scope_key, summary, status, run_id, message_id,
                          job_status
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
            job_status=row["job_status"],
        )
