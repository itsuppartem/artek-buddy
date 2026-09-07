from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from artek_buddy.contracts.domain import (
    Routine,
)
from artek_buddy.cron import CronError, next_run_at, parse_cron, validate_timezone
from artek_buddy.db.shaping import (
    isoformat_utc,
    new_id,
    parse_iso,
)

log = logging.getLogger("artek_buddy")


class RoutinesMixin:
    def create_routine(
        self,
        bot_id: str,
        name: str,
        prompt: str,
        cron: str,
        timezone_name: str = "UTC",
        notify: bool = True,
        active: bool = False,
        require_approval: bool = False,
    ) -> Routine:
        parse_cron(cron)
        zone = validate_timezone(timezone_name)
        now = datetime.now(UTC)
        nxt = isoformat_utc(next_run_at(cron, now, zone)) if active else None
        routine_id = new_id("rtn")
        created = isoformat_utc(now)
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO routines (
                    id, bot_id, name, prompt, cron, timezone, active, notify,
                    last_run_at, next_run_at, created_at, require_approval, definition_version
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, NULL, %s, %s, %s, 1)
                """,
                (
                    routine_id,
                    bot_id,
                    name.strip(),
                    prompt,
                    cron.strip(),
                    zone,
                    active,
                    notify,
                    nxt,
                    created,
                    require_approval,
                ),
            )
            conn.commit()
        created_routine = Routine(
            id=routine_id,
            bot_id=bot_id,
            name=name.strip(),
            prompt=prompt,
            cron=cron.strip(),
            timezone=zone,
            active=active,
            notify=notify,
            last_run_at=None,
            next_run_at=nxt,
            created_at=created,
            require_approval=require_approval,
            definition_version=1,
        )
        self.upsert_automation_from_routine(created_routine)
        return created_routine

    def list_routines(self, bot_id: str) -> list[Routine]:
        with self._conn() as conn:
            rows = conn.execute(
                """
                SELECT r.id, r.bot_id, r.name, r.prompt, r.cron, r.timezone, r.active, r.notify,
                       r.last_run_at, r.next_run_at, r.created_at, r.require_approval,
                       r.definition_version, ar.state AS last_run_state
                FROM routines r
                LEFT JOIN LATERAL (
                    SELECT state FROM automation_runs
                    WHERE routine_id = r.id
                    ORDER BY created_at DESC
                    LIMIT 1
                ) ar ON true
                WHERE r.bot_id = %s
                ORDER BY r.created_at DESC
                """,
                (bot_id,),
            ).fetchall()
            conn.commit()
        return [self._routine_from_row(row) for row in rows]

    def get_routine(self, routine_id: str) -> Routine | None:
        with self._conn() as conn:
            row = conn.execute(
                """
                SELECT r.id, r.bot_id, r.name, r.prompt, r.cron, r.timezone, r.active, r.notify,
                       r.last_run_at, r.next_run_at, r.created_at, r.require_approval,
                       r.definition_version, ar.state AS last_run_state
                FROM routines r
                LEFT JOIN LATERAL (
                    SELECT state FROM automation_runs
                    WHERE routine_id = r.id
                    ORDER BY created_at DESC
                    LIMIT 1
                ) ar ON true
                WHERE r.id = %s
                """,
                (routine_id,),
            ).fetchone()
            conn.commit()
        return self._routine_from_row(row) if row else None

    def update_routine(
        self,
        routine_id: str,
        name: str | None = None,
        prompt: str | None = None,
        cron: str | None = None,
        timezone_name: str | None = None,
        notify: bool | None = None,
        active: bool | None = None,
        require_approval: bool | None = None,
    ) -> Routine | None:
        current = self.get_routine(routine_id)
        if current is None:
            return None
        next_name = name.strip() if name is not None else current.name
        next_prompt = prompt if prompt is not None else current.prompt
        next_cron = cron.strip() if cron is not None else current.cron
        next_zone = (
            validate_timezone(timezone_name) if timezone_name is not None else current.timezone
        )
        next_notify = current.notify if notify is None else notify
        next_active = current.active if active is None else active
        next_approval = current.require_approval if require_approval is None else require_approval
        definition_changed = (
            next_name != current.name
            or next_prompt != current.prompt
            or next_cron != current.cron
            or next_approval != current.require_approval
        )
        next_version = current.definition_version + (1 if definition_changed else 0)
        parse_cron(next_cron)
        nxt = (
            isoformat_utc(next_run_at(next_cron, datetime.now(UTC), next_zone))
            if next_active
            else None
        )
        with self._conn() as conn:
            row = conn.execute(
                """
                UPDATE routines
                SET name = %s, prompt = %s, cron = %s, timezone = %s,
                    notify = %s, active = %s, next_run_at = %s,
                    require_approval = %s, definition_version = %s
                WHERE id = %s
                RETURNING id, bot_id, name, prompt, cron, timezone, active, notify,
                          last_run_at, next_run_at, created_at, require_approval,
                          definition_version
                """,
                (
                    next_name,
                    next_prompt,
                    next_cron,
                    next_zone,
                    next_notify,
                    next_active,
                    nxt,
                    next_approval,
                    next_version,
                    routine_id,
                ),
            ).fetchone()
            if row is not None and (
                next_approval != current.require_approval or next_active != current.active
            ):
                self._append_audit_event_tx(
                    conn,
                    "automation.updated",
                    "owner",
                    routine_id,
                    {
                        "require_approval": next_approval,
                        "active": next_active,
                        "definition_version": next_version,
                    },
                )
            conn.commit()
        updated = self._routine_from_row(row) if row else None
        if updated is not None:
            self.upsert_automation_from_routine(updated)
        return updated

    def delete_routine(self, routine_id: str) -> bool:
        with self._conn() as conn:
            row = conn.execute(
                "DELETE FROM routines WHERE id = %s RETURNING id",
                (routine_id,),
            ).fetchone()
            conn.commit()
        return row is not None

    def claim_due_routines(self, limit: int = 20) -> list[Routine]:
        now = datetime.now(UTC)
        lease_until = now + timedelta(minutes=5)
        claimed: list[Routine] = []
        with self._conn() as conn:
            rows = conn.execute(
                """
                SELECT id, bot_id, name, prompt, cron, timezone, active, notify,
                       last_run_at, next_run_at, created_at, require_approval, definition_version
                FROM routines
                WHERE active
                  AND next_run_at IS NOT NULL
                  AND next_run_at <= %s
                  AND (lease_until IS NULL OR lease_until <= %s)
                ORDER BY next_run_at
                LIMIT %s
                FOR UPDATE SKIP LOCKED
                """,
                (now, now, limit),
            ).fetchall()
            for row in rows:
                try:
                    parse_cron(row["cron"])
                except CronError:
                    conn.execute(
                        "UPDATE routines SET active = FALSE, lease_until = NULL WHERE id = %s",
                        (row["id"],),
                    )
                    continue
                seen = isoformat_utc(now)
                conn.execute(
                    """
                    UPDATE routines
                    SET last_run_at = %s, lease_until = %s
                    WHERE id = %s
                    """,
                    (seen, isoformat_utc(lease_until), row["id"]),
                )
                claimed.append(self._routine_from_row(row).model_copy(update={"last_run_at": seen}))
            conn.commit()
        return claimed

    def ack_routine(self, routine_id: str) -> None:
        now = datetime.now(UTC)
        with self._conn() as conn:
            row = conn.execute(
                "SELECT cron, timezone FROM routines WHERE id = %s AND active",
                (routine_id,),
            ).fetchone()
            if row is None:
                conn.commit()
                return
            try:
                nxt = next_run_at(row["cron"], now, row["timezone"] or "UTC")
            except CronError:
                conn.execute(
                    "UPDATE routines SET active = FALSE, lease_until = NULL WHERE id = %s",
                    (routine_id,),
                )
                conn.commit()
                return
            conn.execute(
                """
                UPDATE routines
                SET next_run_at = %s, lease_until = NULL
                WHERE id = %s
                """,
                (isoformat_utc(nxt), routine_id),
            )
            conn.commit()

    def reschedule_routine(self, routine_id: str, when: str) -> None:
        with self._conn() as conn:
            conn.execute(
                """
                UPDATE routines
                SET next_run_at = %s, lease_until = NULL
                WHERE id = %s AND active
                """,
                (when, routine_id),
            )
            conn.commit()

    def _routine_from_row(self, row: dict[str, Any]) -> Routine:
        return Routine(
            id=row["id"],
            bot_id=row["bot_id"],
            name=row["name"],
            prompt=row["prompt"],
            cron=row["cron"],
            timezone=row["timezone"] or "UTC",
            active=bool(row["active"]),
            notify=bool(row["notify"]),
            last_run_at=parse_iso(row["last_run_at"]) if row["last_run_at"] else None,
            next_run_at=parse_iso(row["next_run_at"]) if row["next_run_at"] else None,
            created_at=parse_iso(row["created_at"]),
            require_approval=bool(row["require_approval"]) if "require_approval" in row else False,
            definition_version=(
                int(row["definition_version"]) if row.get("definition_version") else 1
            ),
            last_run_state=str(row["last_run_state"]) if row.get("last_run_state") else None,
        )
