from __future__ import annotations

import json
import logging
from typing import Any

from artek_buddy.audit import (
    AUDIT_COLLABORATION_OFF,
    AUDIT_INVITE_CLAIM,
    AUDIT_INVITE_MINT,
    AUDIT_INVITE_REVOKE,
    GENESIS_HASH,
    AuditRecord,
    AuditVerificationResult,
    canonical_payload_json,
    compute_audit_hash,
    verify_audit_chain,
)
from artek_buddy.db.shaping import isoformat_utc, new_id, parse_iso

log = logging.getLogger("artek_buddy")

AUDIT_LOCK_KEY = 149060


class AuditMixin:
    def _audit_record_from_row(self, row: dict[str, Any]) -> AuditRecord:
        raw_payload = row["payload"]
        if isinstance(raw_payload, str):
            payload = json.loads(raw_payload)
        else:
            payload = dict(raw_payload)
        return AuditRecord(
            seq=int(row["seq"]),
            id=str(row["id"]),
            event_type=str(row["event_type"]),
            actor=str(row["actor"]),
            resource=str(row["resource"]),
            payload=payload,
            prev_hash=str(row["prev_hash"]),
            hash=str(row["hash"]),
            created_at=parse_iso(row["created_at"]) or str(row["created_at"]),
        )

    def append_audit_event(
        self,
        event_type: str,
        actor: str,
        resource: str,
        payload: dict[str, Any],
        conn: Any | None = None,
    ) -> AuditRecord:
        """Append an audit event inside the given transaction (or open one)."""
        if conn is not None:
            return self._append_audit_event_tx(conn, event_type, actor, resource, payload)

        with self._conn() as new_conn:
            record = self._append_audit_event_tx(new_conn, event_type, actor, resource, payload)
            new_conn.commit()
            return record

    def _append_audit_event_tx(
        self,
        conn: Any,
        event_type: str,
        actor: str,
        resource: str,
        payload: dict[str, Any],
    ) -> AuditRecord:
        conn.execute("SELECT pg_advisory_xact_lock(%s)", (AUDIT_LOCK_KEY,))
        last = conn.execute("SELECT seq, hash FROM audit ORDER BY seq DESC LIMIT 1").fetchone()
        if last is not None:
            seq = int(last["seq"]) + 1
            prev_hash = str(last["hash"])
        else:
            seq = 1
            prev_hash = GENESIS_HASH

        audit_id = new_id("aud")
        payload_json = canonical_payload_json(payload)
        computed_hash = compute_audit_hash(
            seq,
            event_type,
            actor,
            resource,
            payload_json,
            prev_hash,
        )
        now = isoformat_utc()

        conn.execute(
            """
            INSERT INTO audit (
                seq, id, event_type, actor, resource, payload, prev_hash, hash, created_at
            )
            VALUES (%s, %s, %s, %s, %s, %s::jsonb, %s, %s, %s)
            """,
            (
                seq,
                audit_id,
                event_type,
                actor,
                resource,
                payload_json,
                prev_hash,
                computed_hash,
                now,
            ),
        )
        return AuditRecord(
            seq=seq,
            id=audit_id,
            event_type=event_type,
            actor=actor,
            resource=resource,
            payload=json.loads(payload_json),
            prev_hash=prev_hash,
            hash=computed_hash,
            created_at=now,
        )

    def list_audit_events(self, limit: int = 100, offset: int = 0) -> list[AuditRecord]:
        with self._conn() as conn:
            rows = conn.execute(
                """
                SELECT seq, id, event_type, actor, resource, payload, prev_hash, hash, created_at
                FROM audit
                ORDER BY seq ASC
                LIMIT %s OFFSET %s
                """,
                (limit, offset),
            ).fetchall()
            conn.commit()
        return [self._audit_record_from_row(r) for r in rows]

    def get_audit_chain(self) -> list[AuditRecord]:
        with self._conn() as conn:
            rows = conn.execute(
                """
                SELECT seq, id, event_type, actor, resource, payload, prev_hash, hash, created_at
                FROM audit
                ORDER BY seq ASC
                """
            ).fetchall()
            conn.commit()
        return [self._audit_record_from_row(r) for r in rows]

    def verify_audit(self) -> AuditVerificationResult:
        records = self.get_audit_chain()
        return verify_audit_chain(records)

    def emergency_collaboration_off(self, actor: str = "mem_owner") -> AuditRecord:
        with self._conn() as conn:
            conn.execute(
                "UPDATE members SET state = 'suspended' WHERE role != 'owner' AND state = 'active'"
            )
            record = self._append_audit_event_tx(
                conn,
                AUDIT_COLLABORATION_OFF,
                actor=actor,
                resource="workspace",
                payload={"collaboration": False},
            )
            conn.commit()
            return record

    def record_invite_mint(
        self, invite_id: str, role: str, max_uses: int = 1, actor: str = "mem_owner"
    ) -> AuditRecord:
        return self.append_audit_event(
            AUDIT_INVITE_MINT,
            actor=actor,
            resource=invite_id,
            payload={"id": invite_id, "role": role, "max_uses": max_uses},
        )

    def record_invite_claim(
        self, invite_id: str, member_id: str, device_id: str, actor: str
    ) -> AuditRecord:
        return self.append_audit_event(
            AUDIT_INVITE_CLAIM,
            actor=actor,
            resource=invite_id,
            payload={"id": invite_id, "member_id": member_id, "device_id": device_id},
        )

    def record_invite_revoke(self, invite_id: str, actor: str = "mem_owner") -> AuditRecord:
        return self.append_audit_event(
            AUDIT_INVITE_REVOKE,
            actor=actor,
            resource=invite_id,
            payload={"id": invite_id, "action": "revoke"},
        )
