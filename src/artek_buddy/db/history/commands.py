"""Owner command ids so a lost HTTP send can be retried without a second run."""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from artek_buddy.db.shaping import isoformat_utc

NEEDS_SETUP_RUN_ID = "needs_setup"


def owner_command_is_needs_setup(run_id: str) -> bool:
    return run_id == NEEDS_SETUP_RUN_ID


class CommandPayloadConflict(Exception):
    """Same command id, different message or files."""


def _inline_file_digest(name: str, content_base64: str) -> dict[str, str | int]:
    blob = content_base64 or ""
    try:
        data = base64.b64decode(blob, validate=True)
    except (binascii.Error, ValueError):
        data = blob.encode("utf-8")
    return {
        "name": name,
        "sha256": hashlib.sha256(data).hexdigest(),
        "size": len(data),
    }


def _attachment_file_digests(attachments: list[Any] | None) -> list[dict[str, str | int]]:
    files: list[dict[str, str | int]] = []
    for item in attachments or []:
        if isinstance(item, Mapping):
            name = str(item.get("name") or "")
            encoded = str(item.get("content_base64") or item.get("contentBase64") or "")
        else:
            name = str(getattr(item, "name", "") or "")
            encoded = str(getattr(item, "content_base64", "") or "")
        files.append(_inline_file_digest(name, encoded))
    files.sort(key=lambda row: (str(row["name"]), str(row["sha256"]), int(row["size"])))
    return files


def owner_command_fingerprint(
    text: str,
    *,
    reply_to_id: str | None = None,
    attachment_ids: list[str] | None = None,
    attachment_names: list[str] | None = None,
    attachments: list[Any] | None = None,
) -> str:
    files = _attachment_file_digests(attachments)
    payload = {
        "attachment_files": files,
        "attachment_ids": sorted(attachment_ids or []),
        "attachment_names": [] if files else sorted(attachment_names or []),
        "reply_to_id": reply_to_id or "",
        "text": (text or "").strip(),
    }
    blob = json.dumps(payload, separators=(",", ":"), sort_keys=True)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class OwnerCommand:
    command_id: str
    bot_id: str
    payload_hash: str
    run_id: str
    message_id: str | None
    parent_command_id: str | None


def _command_from_row(row: dict[str, Any]) -> OwnerCommand:
    return OwnerCommand(
        command_id=str(row["command_id"]),
        bot_id=str(row["bot_id"]),
        payload_hash=str(row["payload_hash"]),
        run_id=str(row["run_id"]),
        message_id=str(row["message_id"]) if row.get("message_id") else None,
        parent_command_id=str(row["parent_command_id"]) if row.get("parent_command_id") else None,
    )


class CommandsMixin:
    def get_owner_command(self, bot_id: str, command_id: str) -> OwnerCommand | None:
        if not bot_id or not command_id:
            return None
        with self._conn() as conn:
            row = conn.execute(
                """
                SELECT command_id, bot_id, payload_hash, run_id, message_id, parent_command_id
                FROM owner_commands
                WHERE command_id = %s AND bot_id = %s
                """,
                (command_id, bot_id),
            ).fetchone()
            conn.commit()
        return _command_from_row(row) if row else None

    def require_owner_command_payload(
        self, bot_id: str, command_id: str, payload_hash: str
    ) -> OwnerCommand | None:
        found = self.get_owner_command(bot_id, command_id)
        if found is None:
            return None
        if found.payload_hash != payload_hash:
            raise CommandPayloadConflict
        return found

    def record_needs_setup_owner_command(
        self,
        bot_id: str,
        command_id: str,
        payload_hash: str,
        message_id: str,
        parent_command_id: str | None = None,
    ) -> None:
        now = isoformat_utc()
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO owner_commands (
                    command_id, bot_id, payload_hash, run_id, message_id,
                    parent_command_id, created_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    command_id,
                    bot_id,
                    payload_hash,
                    NEEDS_SETUP_RUN_ID,
                    message_id,
                    parent_command_id,
                    now,
                ),
            )
            conn.commit()
