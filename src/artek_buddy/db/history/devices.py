from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Any

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

    def create_device(self, name: str, platform: str = "linux") -> DeviceCreated:
        token = new_device_token()
        now = isoformat_utc()
        device_id = new_id("dev")
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO devices (id, name, platform, token_hash, created_at)
                VALUES (%s, %s, %s, %s, %s)
                """,
                (device_id, name.strip(), platform.strip() or "linux", hash_secret(token), now),
            )
            conn.commit()
        return DeviceCreated(
            id=device_id,
            name=name.strip(),
            platform=platform.strip() or "linux",
            created_at=now,
            token=token,
        )

    def list_devices(self) -> list[Device]:
        with self._conn() as conn:
            rows = conn.execute(
                """
                SELECT id, name, platform, created_at, last_seen_at, revoked_at
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
                SELECT id, name, platform, created_at, last_seen_at, revoked_at
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
                SELECT id, name, platform, created_at, last_seen_at, revoked_at
                FROM devices
                WHERE token_hash = %s AND revoked_at IS NULL
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
                RETURNING id, name, platform, created_at, last_seen_at, revoked_at
                """,
                (now, device_id),
            ).fetchone()
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
            last_seen_at=parse_iso(row["last_seen_at"]) if row["last_seen_at"] else None,
            revoked_at=parse_iso(row["revoked_at"]) if row["revoked_at"] else None,
        )
