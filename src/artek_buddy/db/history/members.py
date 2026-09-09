from __future__ import annotations

import logging
from typing import Any

from artek_buddy.audit import (
    AUDIT_MEMBER_ACTIVATE,
    AUDIT_MEMBER_CREATE,
    AUDIT_MEMBER_SUSPEND,
)
from artek_buddy.auth import hash_secret
from artek_buddy.contracts.domain import Member, Principal
from artek_buddy.db.shaping import isoformat_utc

log = logging.getLogger("artek_buddy")


class MembersMixin:
    def _member_from_row(self, row: Any) -> Member:
        return Member(
            id=row["id"],
            name=row["name"],
            role=row["role"],
            state=row["state"],
            created_at=isoformat_utc(row["created_at"]),
            updated_at=isoformat_utc(row["updated_at"]),
        )

    def ensure_owner_member(self) -> Member:
        with self._conn() as conn:
            row = conn.execute(
                """
                INSERT INTO members (id, name, role, state, created_at, updated_at)
                VALUES ('mem_owner', 'Owner', 'owner', 'active', now(), now())
                ON CONFLICT (id) DO UPDATE SET updated_at = now()
                RETURNING id, name, role, state, created_at, updated_at, (xmax = 0) AS inserted
                """
            ).fetchone()
            inserted = bool(row["inserted"]) if row is not None else False
            if hasattr(self, "_append_audit_event_tx"):
                self._append_audit_event_tx(
                    conn,
                    AUDIT_MEMBER_CREATE,
                    actor="system",
                    resource="mem_owner",
                    payload={
                        "id": "mem_owner",
                        "name": "Owner",
                        "role": "owner",
                        "state": "active",
                    },
                )
            if inserted and hasattr(self, "_append_activity_tx"):
                self._append_activity_tx(
                    conn,
                    event_type="member.created",
                    actor="system",
                    resource="mem_owner",
                    payload={"id": "mem_owner", "name": "Owner", "role": "owner"},
                    device_id=None,
                    event_version=1,
                )
            conn.commit()
        return self._member_from_row(row)

    def get_member(self, member_id: str) -> Member | None:
        with self._conn() as conn:
            row = conn.execute(
                """
                SELECT id, name, role, state, created_at, updated_at
                FROM members WHERE id = %s
                """,
                (member_id,),
            ).fetchone()
            conn.commit()
        return self._member_from_row(row) if row else None

    def get_owner_member(self) -> Member:
        member = self.get_member("mem_owner")
        if member is None:
            return self.ensure_owner_member()
        return member

    def list_members(self) -> list[Member]:
        with self._conn() as conn:
            rows = conn.execute(
                """
                SELECT id, name, role, state, created_at, updated_at
                FROM members ORDER BY created_at ASC
                """
            ).fetchall()
            conn.commit()
        return [self._member_from_row(r) for r in rows]

    def suspend_member(self, member_id: str) -> Member | None:
        now = isoformat_utc()
        with self._conn() as conn:
            row = conn.execute(
                """
                UPDATE members
                SET state = 'suspended', updated_at = %s
                WHERE id = %s
                RETURNING id, name, role, state, created_at, updated_at
                """,
                (now, member_id),
            ).fetchone()
            if row is not None and hasattr(self, "_append_audit_event_tx"):
                self._append_audit_event_tx(
                    conn,
                    AUDIT_MEMBER_SUSPEND,
                    actor="mem_owner",
                    resource=member_id,
                    payload={"id": member_id, "state": "suspended"},
                )
            if row is not None and hasattr(self, "_append_activity_tx"):
                self._append_activity_tx(
                    conn,
                    event_type="member.suspended",
                    actor="mem_owner",
                    resource=member_id,
                    payload={"id": member_id, "state": "suspended"},
                    device_id=None,
                    event_version=1,
                )
            conn.commit()
        return self._member_from_row(row) if row else None

    def activate_member(self, member_id: str) -> Member | None:
        now = isoformat_utc()
        with self._conn() as conn:
            row = conn.execute(
                """
                UPDATE members
                SET state = 'active', updated_at = %s
                WHERE id = %s
                RETURNING id, name, role, state, created_at, updated_at
                """,
                (now, member_id),
            ).fetchone()
            if row is not None and hasattr(self, "_append_audit_event_tx"):
                self._append_audit_event_tx(
                    conn,
                    AUDIT_MEMBER_ACTIVATE,
                    actor="mem_owner",
                    resource=member_id,
                    payload={"id": member_id, "state": "active"},
                )
            if row is not None and hasattr(self, "_append_activity_tx"):
                self._append_activity_tx(
                    conn,
                    event_type="member.activated",
                    actor="mem_owner",
                    resource=member_id,
                    payload={"id": member_id, "state": "active"},
                    device_id=None,
                    event_version=1,
                )
            conn.commit()
        return self._member_from_row(row) if row else None

    def lookup_principal(self, token: str) -> Principal | None:
        if not token:
            return None
        with self._conn() as conn:
            row = conn.execute(
                """
                SELECT d.id AS device_id, d.member_id, m.role, m.state
                FROM devices d
                JOIN members m ON d.member_id = m.id
                WHERE d.token_hash = %s
                  AND d.revoked_at IS NULL
                  AND m.state = 'active'
                """,
                (hash_secret(token),),
            ).fetchone()
            conn.commit()
        if row is None:
            return None
        return Principal(
            member_id=row["member_id"],
            device_id=row["device_id"],
            role=row["role"],
        )
