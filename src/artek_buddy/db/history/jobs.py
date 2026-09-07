from __future__ import annotations

import json
import logging
from typing import Any

from artek_buddy.db.shaping import isoformat_utc, new_id, parse_iso
from artek_buddy.jobs import (
    JobRecord,
    calculate_backoff_seconds,
)

log = logging.getLogger("artek_buddy.jobs")


class JobsMixin:
    def _job_record_from_row(self, row: dict[str, Any]) -> JobRecord:
        raw_payload = row["payload"]
        if isinstance(raw_payload, str):
            payload = json.loads(raw_payload)
        else:
            payload = dict(raw_payload or {})

        raw_result = row["result"]
        if isinstance(raw_result, str):
            result = json.loads(raw_result)
        elif raw_result:
            result = dict(raw_result)
        else:
            result = None

        return JobRecord(
            id=str(row["id"]),
            job_type=str(row["job_type"]),
            resource_id=str(row["resource_id"]) if row.get("resource_id") else None,
            idempotency_key=str(row["idempotency_key"]) if row.get("idempotency_key") else None,
            state=str(row["state"]),
            payload=payload,
            result=result,
            last_error=str(row["last_error"]) if row.get("last_error") else None,
            attempts=int(row["attempts"]),
            max_attempts=int(row["max_attempts"]),
            lease_owner=str(row["lease_owner"]) if row.get("lease_owner") else None,
            lease_expires_at=(
                parse_iso(row["lease_expires_at"]) if row.get("lease_expires_at") else None
            ),
            run_at=parse_iso(row["run_at"]) or str(row["run_at"]),
            created_at=parse_iso(row["created_at"]) or str(row["created_at"]),
            updated_at=parse_iso(row["updated_at"]) or str(row["updated_at"]),
            completed_at=(
                parse_iso(row["completed_at"]) if row.get("completed_at") else None
            ),
        )

    def enqueue_job(
        self,
        job_type: str,
        payload: dict[str, Any],
        *,
        resource_id: str | None = None,
        idempotency_key: str | None = None,
        max_attempts: int = 5,
        run_at: str | None = None,
    ) -> JobRecord:
        now = isoformat_utc()
        target_run_at = run_at or now

        with self._conn() as conn:
            if idempotency_key:
                existing = conn.execute(
                    """
                    SELECT id, job_type, resource_id, idempotency_key, state, payload, result,
                           last_error, attempts, max_attempts, lease_owner, lease_expires_at,
                           run_at, created_at, updated_at, completed_at
                    FROM jobs
                    WHERE idempotency_key = %s
                    """,
                    (idempotency_key,),
                ).fetchone()
                if existing is not None:
                    conn.commit()
                    return self._job_record_from_row(existing)

            job_id = new_id("job")
            payload_json = json.dumps(payload, ensure_ascii=False)
            row = conn.execute(
                """
                INSERT INTO jobs (
                    id, job_type, resource_id, idempotency_key, state, payload,
                    attempts, max_attempts, run_at, created_at, updated_at
                )
                VALUES (%s, %s, %s, %s, 'queued', %s::jsonb, 0, %s, %s, %s, %s)
                RETURNING id, job_type, resource_id, idempotency_key, state, payload, result,
                          last_error, attempts, max_attempts, lease_owner, lease_expires_at,
                          run_at, created_at, updated_at, completed_at
                """,
                (
                    job_id,
                    job_type,
                    resource_id,
                    idempotency_key,
                    payload_json,
                    max_attempts,
                    target_run_at,
                    now,
                    now,
                ),
            ).fetchone()
            conn.commit()
        return self._job_record_from_row(row)

    def claim_jobs(
        self,
        worker_id: str,
        limit: int = 5,
        lease_seconds: int = 300,
    ) -> list[JobRecord]:
        claimed: list[JobRecord] = []
        with self._conn() as conn:
            rows = conn.execute(
                """
                SELECT id, job_type, resource_id, idempotency_key, state, payload, result,
                       last_error, attempts, max_attempts, lease_owner, lease_expires_at,
                       run_at, created_at, updated_at, completed_at
                FROM jobs
                WHERE (
                    (state = 'queued' AND run_at <= now())
                    OR (state = 'running' AND lease_expires_at <= now())
                )
                ORDER BY run_at ASC, created_at ASC
                LIMIT %s
                FOR UPDATE SKIP LOCKED
                """,
                (limit,),
            ).fetchall()

            for r in rows:
                updated = conn.execute(
                    """
                    UPDATE jobs
                    SET state = 'running',
                        lease_owner = %s,
                        lease_expires_at = now() + (%s || ' seconds')::interval,
                        attempts = attempts + 1,
                        updated_at = now()
                    WHERE id = %s
                    RETURNING id, job_type, resource_id, idempotency_key, state, payload, result,
                              last_error, attempts, max_attempts, lease_owner, lease_expires_at,
                              run_at, created_at, updated_at, completed_at
                    """,
                    (worker_id, lease_seconds, r["id"]),
                ).fetchone()
                if updated:
                    claimed.append(self._job_record_from_row(updated))
            conn.commit()
        return claimed

    def ack_job(self, job_id: str, result: dict[str, Any] | None = None) -> bool:
        result_json = json.dumps(result, ensure_ascii=False) if result is not None else None
        with self._conn() as conn:
            row = conn.execute(
                """
                UPDATE jobs
                SET state = 'succeeded',
                    result = %s::jsonb,
                    completed_at = now(),
                    lease_owner = NULL,
                    lease_expires_at = NULL,
                    updated_at = now()
                WHERE id = %s AND state = 'running'
                RETURNING id
                """,
                (result_json, job_id),
            ).fetchone()
            conn.commit()
        return row is not None

    def fail_job(
        self,
        job_id: str,
        error: str,
        backoff_seconds: float | None = None,
    ) -> bool:
        with self._conn() as conn:
            job_row = conn.execute(
                "SELECT attempts, max_attempts FROM jobs WHERE id = %s",
                (job_id,),
            ).fetchone()
            if not job_row:
                conn.commit()
                return False

            attempts = int(job_row["attempts"])
            max_attempts = int(job_row["max_attempts"])

            if attempts >= max_attempts:
                # Max retries exceeded -> dead letter
                row = conn.execute(
                    """
                    UPDATE jobs
                    SET state = 'dead',
                        last_error = %s,
                        lease_owner = NULL,
                        lease_expires_at = NULL,
                        updated_at = now()
                    WHERE id = %s
                    RETURNING id
                    """,
                    (error, job_id),
                ).fetchone()
            else:
                retry_delay = (
                    backoff_seconds
                    if backoff_seconds is not None
                    else calculate_backoff_seconds(attempts)
                )
                row = conn.execute(
                    """
                    UPDATE jobs
                    SET state = 'queued',
                        last_error = %s,
                        run_at = now() + (%s || ' seconds')::interval,
                        lease_owner = NULL,
                        lease_expires_at = NULL,
                        updated_at = now()
                    WHERE id = %s
                    RETURNING id
                    """,
                    (error, retry_delay, job_id),
                ).fetchone()
            conn.commit()
        return row is not None

    def heartbeat_job(
        self,
        job_id: str,
        worker_id: str,
        extend_seconds: int = 300,
    ) -> bool:
        with self._conn() as conn:
            row = conn.execute(
                """
                UPDATE jobs
                SET lease_expires_at = now() + (%s || ' seconds')::interval,
                    updated_at = now()
                WHERE id = %s AND lease_owner = %s AND state = 'running'
                RETURNING id
                """,
                (extend_seconds, job_id, worker_id),
            ).fetchone()
            conn.commit()
        return row is not None

    def cancel_job(self, job_id: str) -> bool:
        with self._conn() as conn:
            row = conn.execute(
                """
                UPDATE jobs
                SET state = 'cancelled',
                    lease_owner = NULL,
                    lease_expires_at = NULL,
                    updated_at = now()
                WHERE id = %s AND state IN ('queued', 'running')
                RETURNING id
                """,
                (job_id,),
            ).fetchone()
            conn.commit()
        return row is not None

    def get_job(self, job_id: str) -> JobRecord | None:
        with self._conn() as conn:
            row = conn.execute(
                """
                SELECT id, job_type, resource_id, idempotency_key, state, payload, result,
                       last_error, attempts, max_attempts, lease_owner, lease_expires_at,
                       run_at, created_at, updated_at, completed_at
                FROM jobs WHERE id = %s
                """,
                (job_id,),
            ).fetchone()
            conn.commit()
        return self._job_record_from_row(row) if row else None

    def list_dead_jobs(self, limit: int = 50) -> list[JobRecord]:
        with self._conn() as conn:
            rows = conn.execute(
                """
                SELECT id, job_type, resource_id, idempotency_key, state, payload, result,
                       last_error, attempts, max_attempts, lease_owner, lease_expires_at,
                       run_at, created_at, updated_at, completed_at
                FROM jobs
                WHERE state = 'dead'
                ORDER BY updated_at DESC
                LIMIT %s
                """,
                (limit,),
            ).fetchall()
            conn.commit()
        return [self._job_record_from_row(r) for r in rows]
