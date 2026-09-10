"""Owner command ids so a lost HTTP send can be retried without a second run."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any


class CommandPayloadConflict(Exception):
    """Same command id, different message or files."""


def owner_command_fingerprint(
    text: str,
    *,
    reply_to_id: str | None = None,
    attachment_ids: list[str] | None = None,
    attachment_names: list[str] | None = None,
) -> str:
    payload = {
        "attachment_ids": sorted(attachment_ids or []),
        "attachment_names": sorted(attachment_names or []),
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
