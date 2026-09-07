from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from artek_buddy.audit import AUDIT_DEVICE_CREATE, AUDIT_DEVICE_REVOKE
from artek_buddy.auth import (
    PAIRING_TTL_SECONDS,
    hash_secret,
    new_device_token,
    new_pairing_code,
    normalize_pairing_code,
)
from artek_buddy.contracts.domain import (
    Device,
    DeviceCreated,
    PairingCode,
)
from artek_buddy.db.shaping import (
    isoformat_utc,
    new_id,
    parse_iso,
)

log = logging.getLogger("artek_buddy")


class DevicesMixin:
    def create_pairing_code(self) -> PairingCode:
        code = new_pairing_code()
        now = datetime.now(UTC)
        expires = now + timedelta(seconds=PAIRING_TTL_SECONDS)
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO device_pairing_codes (code_hash, expires_at, created_at)
                VALUES (%s, %s, %s)
                """,
                (hash_secret(normalize_pairing_code(code)), expires, now),
            )
            conn.commit()
        return PairingCode(code=code, expires_at=isoformat_utc(expires))

    def consume_pairing_code(self, code: str) -> bool:
        normalized = normalize_pairing_code(code)
        if len(normalized) < 8:
            return False
        with self._conn() as conn:
            row = conn.execute(
                """
                UPDATE device_pairing_codes
                SET used_at = now()
                WHERE code_hash = %s
                  AND used_at IS NULL
                  AND expires_at > now()
                RETURNING code_hash
                """,
                (hash_secret(normalized),),
            ).fetchone()
            conn.commit()
        return row is not None

    def create_device(
        self,
        name: str,
        platform: str = "linux",
        member_id: str | None = None,
    ) -> DeviceCreated:
        token = new_device_token()
        now = isoformat_utc()
        device_id = new_id("dev")
        target_member_id = member_id or "mem_owner"
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO devices (id, name, platform, token_hash, created_at, member_id)
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (
                    device_id,
                    name.strip(),
                    platform.strip() or "linux",
                    hash_secret(token),
                    now,
                    target_member_id,
                ),
            )
            if hasattr(self, "_append_audit_event_tx"):
                self._append_audit_event_tx(
                    conn,
                    AUDIT_DEVICE_CREATE,
                    actor=target_member_id,
                    resource=device_id,
                    payload={
                        "id": device_id,
                        "name": name.strip(),
                        "platform": platform.strip() or "linux",
                        "member_id": target_member_id,
                    },
                )
            if hasattr(self, "_append_activity_tx"):
                self._append_activity_tx(
                    conn,
                    event_type="device.created",
                    actor=target_member_id,
                    resource=device_id,
                    payload={
                        "id": device_id,
                        "name": name.strip(),
                        "platform": platform.strip() or "linux",
                    },
                    device_id=device_id,
                    event_version=1,
                )
            conn.commit()
        return DeviceCreated(
            id=device_id,
            name=name.strip(),
            platform=platform.strip() or "linux",
            created_at=now,
            token=token,
            member_id=target_member_id,
        )

    def list_devices(self, member_id: str | None = None) -> list[Device]:
        with self._conn() as conn:
            if member_id:
                rows = conn.execute(
                    """
                    SELECT id, name, platform, created_at, last_seen_at, revoked_at, member_id
                    FROM devices
                    WHERE member_id = %s
                    ORDER BY created_at DESC
                    """,
                    (member_id,),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT id, name, platform, created_at, last_seen_at, revoked_at, member_id
                    FROM devices
                    ORDER BY created_at DESC
                    """
                ).fetchall()
            conn.commit()
        return [self._device_from_row(row) for row in rows]

    def get_device(self, device_id: str) -> Device | None:
        with self._conn() as conn:
            row = conn.execute(
                """
                SELECT id, name, platform, created_at, last_seen_at, revoked_at, member_id
                FROM devices WHERE id = %s
                """,
                (device_id,),
            ).fetchone()
            conn.commit()
        return self._device_from_row(row) if row else None

    def lookup_device_token(self, token: str) -> Device | None:
        if not token:
            return None
        with self._conn() as conn:
            row = conn.execute(
                """
                SELECT d.id, d.name, d.platform, d.created_at, d.last_seen_at, d.revoked_at, d.member_id
                FROM devices d
                LEFT JOIN members m ON d.member_id = m.id
                WHERE d.token_hash = %s
                  AND d.revoked_at IS NULL
                  AND (m.state IS NULL OR m.state = 'active')
                """,
                (hash_secret(token),),
            ).fetchone()
            if row is None:
                conn.commit()
                return None
            seen = isoformat_utc()
            conn.execute(
                "UPDATE devices SET last_seen_at = %s WHERE id = %s",
                (seen, row["id"]),
            )
            conn.commit()
        device = self._device_from_row(row)
        return device.model_copy(update={"last_seen_at": seen})

    def revoke_device(self, device_id: str) -> Device | None:
        now = isoformat_utc()
        with self._conn() as conn:
            row = conn.execute(
                """
                UPDATE devices
                SET revoked_at = COALESCE(revoked_at, %s)
                WHERE id = %s AND revoked_at IS NULL
                RETURNING id, name, platform, created_at, last_seen_at, revoked_at, member_id
                """,
                (now, device_id),
            ).fetchone()
            if row is not None and hasattr(self, "_append_audit_event_tx"):
                actor = str(row.get("member_id") or "mem_owner")
                self._append_audit_event_tx(
                    conn,
                    AUDIT_DEVICE_REVOKE,
                    actor=actor,
                    resource=device_id,
                    payload={"id": device_id, "revoked_at": now},
                )
            if row is not None and hasattr(self, "_append_activity_tx"):
                actor = str(row.get("member_id") or "mem_owner")
                self._append_activity_tx(
                    conn,
                    event_type="device.revoked",
                    actor=actor,
                    resource=device_id,
                    payload={"id": device_id, "revoked_at": now},
                    device_id=device_id,
                    event_version=1,
                )
            conn.commit()
        return self._device_from_row(row) if row else None

    def delete_device(self, device_id: str) -> bool:
        with self._conn() as conn:
            row = conn.execute(
                "DELETE FROM devices WHERE id = %s RETURNING id",
                (device_id,),
            ).fetchone()
            conn.commit()
        return row is not None

    def delete_pairing_hash(self, code_hash: str) -> None:
        with self._conn() as conn:
            conn.execute("DELETE FROM device_pairing_codes WHERE code_hash = %s", (code_hash,))
            conn.commit()

    def _device_from_row(self, row: dict[str, Any]) -> Device:
        return Device(
            id=row["id"],
            name=row["name"],
            platform=row["platform"] or "linux",
            created_at=parse_iso(row["created_at"]),
            last_seen_at=parse_iso(row["last_seen_at"]) if row.get("last_seen_at") else None,
            revoked_at=parse_iso(row["revoked_at"]) if row.get("revoked_at") else None,
            member_id=row.get("member_id"),
        )
