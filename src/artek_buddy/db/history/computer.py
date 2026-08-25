from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from artek_buddy.computer.models import ComputerRecord
from artek_buddy.contracts.domain import (
    Bot,
)
from artek_buddy.db.shaping import (
    isoformat_utc,
    new_id,
    parse_iso,
)

log = logging.getLogger("artek_buddy")


class ComputerMixin:
    def ensure_computer(self, bot: Bot) -> ComputerRecord:
        if bot.computer_mode == "dedicated":
            scope, scope_key, home_key = "dedicated", f"bot:{bot.id}", bot.id
        else:
            scope, scope_key, home_key = (
                "team",
                f"team:{bot.workspace_id}",
                f"team-{bot.workspace_id}",
            )
        now = isoformat_utc()
        with self._conn() as conn:
            with conn.transaction():
                row = conn.execute(
                    "SELECT * FROM computers WHERE scope_key = %s",
                    (scope_key,),
                ).fetchone()
                if row is None:
                    computer_id = new_id("cmp")
                    conn.execute(
                        """
                        INSERT INTO computers (
                            id, workspace_id, scope, scope_key, home_key, home_revision,
                            kind, provider_ref, state, control_holder, created_at, updated_at
                        ) VALUES (%s, %s, %s, %s, %s, 'empty', 'docker', NULL, 'stopped', 'none', %s, %s)
                        """,
                        (computer_id, bot.workspace_id, scope, scope_key, home_key, now, now),
                    )
                    row = conn.execute(
                        "SELECT * FROM computers WHERE id = %s", (computer_id,)
                    ).fetchone()
                conn.execute(
                    "UPDATE bots SET computer_id = %s, updated_at = %s WHERE id = %s",
                    (row["id"], now, bot.id),
                )
        return self._computer_from_row(row)

    def get_computer(self, computer_id: str) -> ComputerRecord | None:
        with self._conn() as conn:
            row = conn.execute("SELECT * FROM computers WHERE id = %s", (computer_id,)).fetchone()
            conn.commit()
        return self._computer_from_row(row) if row else None

    def get_computer_for_bot(self, bot: Bot) -> ComputerRecord:
        return self.ensure_computer(bot)

    def save_computer(self, record: ComputerRecord) -> ComputerRecord:
        now = isoformat_utc()
        with self._conn() as conn:
            row = conn.execute(
                """
                UPDATE computers SET
                    home_revision = %s, kind = %s, provider_ref = %s, state = %s,
                    control_holder = %s, control_lease_id = %s, control_lease_expires_at = %s,
                    control_bot_id = %s, execution_run_id = %s, execution_bot_id = %s,
                    execution_lease_expires_at = %s, sleep_at = %s, last_input_at = %s,
                    updated_at = %s
                WHERE id = %s
                RETURNING *
                """,
                (
                    record.home_revision,
                    record.kind,
                    record.provider_ref,
                    record.state,
                    record.control_holder,
                    record.control_lease_id,
                    record.control_lease_expires_at,
                    record.control_bot_id,
                    record.execution_run_id,
                    record.execution_bot_id,
                    record.execution_lease_expires_at,
                    record.sleep_at,
                    record.last_input_at,
                    now,
                    record.id,
                ),
            ).fetchone()
            conn.commit()
        if row is None:
            raise RuntimeError("computer missing")
        return self._computer_from_row(row)

    def other_bots_using_computer(self, computer_id: str, except_bot_id: str) -> int:
        with self._conn() as conn:
            row = conn.execute(
                """
                SELECT COUNT(*) AS n
                FROM bots
                WHERE computer_id = %s AND id <> %s
                """,
                (computer_id, except_bot_id),
            ).fetchone()
            conn.commit()
        return int(row["n"]) if row else 0

    def list_orphan_computers(self) -> list[ComputerRecord]:
        with self._conn() as conn:
            rows = conn.execute(
                """
                SELECT c.*
                FROM computers c
                WHERE NOT EXISTS (
                    SELECT 1 FROM bots b WHERE b.computer_id = c.id
                )
                ORDER BY c.updated_at ASC
                """
            ).fetchall()
            conn.commit()
        return [self._computer_from_row(row) for row in rows]

    def delete_computer(self, computer_id: str) -> bool:
        with self._conn() as conn:
            row = conn.execute(
                """
                DELETE FROM computers
                WHERE id = %s
                  AND NOT EXISTS (
                      SELECT 1 FROM bots WHERE bots.computer_id = computers.id
                  )
                RETURNING id
                """,
                (computer_id,),
            ).fetchone()
            conn.commit()
        return row is not None

    def busy_bot_name(self, computer: ComputerRecord, except_bot_id: str) -> str | None:
        holder_id = None
        held = computer.state in {"running", "booting"}
        if computer.scope == "team" and held:
            if computer.execution_bot_id and computer.execution_bot_id != except_bot_id:
                holder_id = computer.execution_bot_id
            elif (
                computer.control_bot_id
                and computer.control_bot_id != except_bot_id
                and computer.control_holder == "user"
            ):
                holder_id = computer.control_bot_id
        if (
            holder_id is None
            and computer.execution_bot_id
            and computer.execution_bot_id != except_bot_id
        ):
            if self.has_active_run(computer.execution_bot_id):
                holder_id = computer.execution_bot_id
        if holder_id:
            other = self.get_bot(holder_id)
            return other.name if other else holder_id
        with self._conn() as conn:
            row = conn.execute(
                """
                SELECT b.name
                FROM bots b
                JOIN runs r ON r.bot_id = b.id
                WHERE b.computer_id = %s
                  AND b.id <> %s
                  AND r.status IN (
                    'queued', 'leased', 'running', 'waiting_input', 'waiting_takeover'
                  )
                LIMIT 1
                """,
                (computer.id, except_bot_id),
            ).fetchone()
            conn.commit()
        return str(row["name"]) if row else None

    def due_idle_computer_bots(self) -> list[str]:
        now = isoformat_utc()
        with self._conn() as conn:
            rows = conn.execute(
                """
                SELECT b.id
                FROM computers c
                JOIN bots b ON b.computer_id = c.id
                WHERE c.state = 'running'
                  AND c.sleep_at IS NOT NULL
                  AND c.sleep_at <= %s
                  AND c.control_holder <> 'user'
                  AND NOT EXISTS (
                    SELECT 1
                    FROM bots other
                    JOIN runs r ON r.bot_id = other.id
                    WHERE other.computer_id = c.id
                      AND r.status IN (
                        'queued', 'leased', 'running', 'waiting_input'
                      )
                  )
                ORDER BY c.sleep_at ASC
                """,
                (now,),
            ).fetchall()
            conn.commit()
        return [row["id"] for row in rows]

    def expire_idle_takeovers(self, idle_seconds: int) -> int:
        cutoff = isoformat_utc(datetime.now(UTC) - timedelta(seconds=max(30, int(idle_seconds))))
        now = isoformat_utc()
        with self._conn() as conn:
            rows = conn.execute(
                """
                UPDATE computers
                SET control_holder = 'bot',
                    control_lease_id = NULL,
                    control_lease_expires_at = NULL,
                    control_bot_id = NULL,
                    last_input_at = NULL,
                    updated_at = %s
                WHERE state = 'running'
                  AND control_holder = 'user'
                  AND COALESCE(last_input_at, updated_at) <= %s
                RETURNING id
                """,
                (now, cutoff),
            ).fetchall()
            conn.commit()
        return len(rows)

    def _computer_from_row(self, row: dict[str, Any]) -> ComputerRecord:
        return ComputerRecord(
            id=row["id"],
            workspace_id=row["workspace_id"],
            scope=row["scope"],
            scope_key=row["scope_key"],
            home_key=row["home_key"],
            home_revision=row.get("home_revision"),
            kind=row.get("kind") or "docker",
            provider_ref=row.get("provider_ref"),
            state=row.get("state") or "stopped",
            control_holder=row.get("control_holder") or "none",
            control_lease_id=row.get("control_lease_id"),
            control_lease_expires_at=parse_iso(row["control_lease_expires_at"])
            if row.get("control_lease_expires_at")
            else None,
            control_bot_id=row.get("control_bot_id"),
            execution_run_id=row.get("execution_run_id"),
            execution_bot_id=row.get("execution_bot_id"),
            execution_lease_expires_at=parse_iso(row["execution_lease_expires_at"])
            if row.get("execution_lease_expires_at")
            else None,
            sleep_at=parse_iso(row["sleep_at"]) if row.get("sleep_at") else None,
            updated_at=parse_iso(row["updated_at"]),
            last_input_at=parse_iso(row["last_input_at"]) if row.get("last_input_at") else None,
        )
