from __future__ import annotations

import json
from typing import Any

from artek_buddy.activity import (
    ACTIVITY_REPLAY_LIMIT,
    DEFAULT_ACTIVITY_RETENTION,
    ActivityRecord,
    sanitize_activity_payload,
)
from artek_buddy.db.shaping import isoformat_utc, new_id, parse_iso


class ActivityMixin:
    def _activity_record_from_row(self, row: dict[str, Any]) -> ActivityRecord:
        raw_payload = row["payload"]
        if isinstance(raw_payload, str):
            payload = json.loads(raw_payload)
        else:
            payload = dict(raw_payload or {})
        return ActivityRecord(
            seq=int(row["seq"]),
            id=str(row["id"]),
            event_type=str(row["event_type"]),
            event_version=int(row["event_version"]),
            actor=str(row["actor"]),
            device_id=str(row["device_id"]) if row.get("device_id") else None,
            resource=str(row["resource"]),
            payload=payload,
            created_at=parse_iso(row["created_at"]) or str(row["created_at"]),
        )

    def append_activity(
        self,
        event_type: str,
        actor: str,
        resource: str,
        payload: dict[str, Any],
        *,
        device_id: str | None = None,
        event_version: int = 1,
        conn: Any | None = None,
    ) -> ActivityRecord:
        if conn is not None:
            return self._append_activity_tx(
                conn, event_type, actor, resource, payload, device_id, event_version
            )

        with self._conn() as new_conn:
            record = self._append_activity_tx(
                new_conn, event_type, actor, resource, payload, device_id, event_version
            )
            new_conn.commit()
        if record.seq > DEFAULT_ACTIVITY_RETENTION * 2:
            self.prune_activity()
        return record

    def _append_activity_tx(
        self,
        conn: Any,
        event_type: str,
        actor: str,
        resource: str,
        payload: dict[str, Any],
        device_id: str | None,
        event_version: int,
    ) -> ActivityRecord:
        act_id = new_id("act")
        sanitized = sanitize_activity_payload(payload)
        payload_json = json.dumps(sanitized, ensure_ascii=False)
        now = isoformat_utc()
        row = conn.execute(
            """
            INSERT INTO activity (
                id, event_type, event_version, actor, device_id, resource, payload, created_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb, %s)
            RETURNING seq
            """,
            (
                act_id,
                event_type,
                event_version,
                actor,
                device_id,
                resource,
                payload_json,
                now,
            ),
        ).fetchone()
        return ActivityRecord(
            seq=int(row["seq"]),
            id=act_id,
            event_type=event_type,
            event_version=event_version,
            actor=actor,
            device_id=device_id,
            resource=resource,
            payload=sanitized,
            created_at=now,
        )

    def replay_activity(
        self,
        after_seq: int | None = None,
        resource: str | None = None,
        limit: int = ACTIVITY_REPLAY_LIMIT,
    ) -> tuple[list[ActivityRecord], bool]:
        has_gap = False
        with self._conn() as conn:
            if after_seq is not None and after_seq > 0:
                min_row = conn.execute("SELECT MIN(seq) AS min_seq FROM activity").fetchone()
                min_seq = (
                    int(min_row["min_seq"])
                    if min_row is not None and min_row["min_seq"] is not None
                    else None
                )
                if min_seq is None or after_seq < (min_seq - 1):
                    has_gap = True

            select_sql = """
                SELECT seq, id, event_type, event_version, actor, device_id,
                       resource, payload, created_at
                FROM activity
            """
            if after_seq is None and resource is None:
                rows = conn.execute(
                    select_sql + " ORDER BY seq ASC LIMIT %s",
                    (limit,),
                ).fetchall()
            elif after_seq is None:
                rows = conn.execute(
                    select_sql + " WHERE resource = %s ORDER BY seq ASC LIMIT %s",
                    (resource, limit),
                ).fetchall()
            elif resource is None:
                rows = conn.execute(
                    select_sql + " WHERE seq > %s ORDER BY seq ASC LIMIT %s",
                    (after_seq, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    select_sql
                    + " WHERE seq > %s AND resource = %s ORDER BY seq ASC LIMIT %s",
                    (after_seq, resource, limit),
                ).fetchall()
            conn.commit()

        return [self._activity_record_from_row(row) for row in rows], has_gap

    def prune_activity(self, retain_count: int = DEFAULT_ACTIVITY_RETENTION) -> int:
        with self._conn() as conn:
            row = conn.execute(
                """
                DELETE FROM activity
                WHERE seq < (
                    SELECT COALESCE(MIN(seq), 0)
                    FROM (
                        SELECT seq FROM activity ORDER BY seq DESC LIMIT %s
                    ) AS recent
                )
                """,
                (retain_count,),
            )
            deleted = int(row.rowcount if hasattr(row, "rowcount") else 0)
            conn.commit()
            return deleted
