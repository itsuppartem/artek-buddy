from __future__ import annotations

import json
from typing import Any

from artek_buddy.contracts.automations import AutomationRun
from artek_buddy.contracts.domain import Bot, Routine
from artek_buddy.contracts.ids import RunStatus
from artek_buddy.db.shaping import isoformat_utc, new_id, parse_iso

APPROVE_LABEL = "Approve"
DENY_LABEL = "Deny"


class AutomationsMixin:
    def upsert_automation_from_routine(self, routine: Routine) -> None:
        now = isoformat_utc()
        state = "enabled" if routine.active else "disabled"
        with self._conn() as conn:
            row = conn.execute(
                "SELECT id FROM automations WHERE routine_id = %s",
                (routine.id,),
            ).fetchone()
            if row is None:
                automation_id = new_id("aut")
                conn.execute(
                    """
                    INSERT INTO automations (
                        id, routine_id, bot_id, name, trigger_kind, cron, timezone,
                        prompt, require_approval, definition_version, state,
                        created_at, updated_at
                    ) VALUES (
                        %s, %s, %s, %s, 'cron', %s, %s,
                        %s, %s, %s, %s,
                        %s, %s
                    )
                    """,
                    (
                        automation_id,
                        routine.id,
                        routine.bot_id,
                        routine.name,
                        routine.cron,
                        routine.timezone,
                        routine.prompt,
                        routine.require_approval,
                        routine.definition_version,
                        state,
                        routine.created_at,
                        now,
                    ),
                )
            else:
                automation_id = str(row["id"])
                conn.execute(
                    """
                    UPDATE automations
                    SET name = %s, cron = %s, timezone = %s, prompt = %s,
                        require_approval = %s, definition_version = %s, state = %s,
                        updated_at = %s
                    WHERE id = %s
                    """,
                    (
                        routine.name,
                        routine.cron,
                        routine.timezone,
                        routine.prompt,
                        routine.require_approval,
                        routine.definition_version,
                        state,
                        now,
                        automation_id,
                    ),
                )
            conn.execute(
                "DELETE FROM automation_steps WHERE automation_id = %s",
                (automation_id,),
            )
            seq = 1
            if routine.require_approval:
                conn.execute(
                    """
                    INSERT INTO automation_steps (id, automation_id, seq, kind, config)
                    VALUES (%s, %s, %s, 'wait_approval', '{}'::jsonb)
                    """,
                    (new_id("astep"), automation_id, seq),
                )
                seq += 1
            conn.execute(
                """
                INSERT INTO automation_steps (id, automation_id, seq, kind, config)
                VALUES (%s, %s, %s, 'prompt_bot', %s::jsonb)
                """,
                (
                    new_id("astep"),
                    automation_id,
                    seq,
                    json.dumps({"prompt": routine.prompt}),
                ),
            )
            conn.execute(
                """
                INSERT INTO automation_steps (id, automation_id, seq, kind, config)
                VALUES (%s, %s, %s, 'stop', '{}'::jsonb)
                """,
                (new_id("astep"), automation_id, seq + 1),
            )
            conn.commit()

    def automation_snapshot(self, routine: Routine) -> dict[str, Any]:
        steps: list[dict[str, Any]] = []
        seq = 1
        if routine.require_approval:
            steps.append({"seq": seq, "kind": "wait_approval"})
            seq += 1
        steps.append({"seq": seq, "kind": "prompt_bot", "prompt": routine.prompt})
        steps.append({"seq": seq + 1, "kind": "stop"})
        return {
            "routine_id": routine.id,
            "bot_id": routine.bot_id,
            "name": routine.name,
            "prompt": routine.prompt,
            "cron": routine.cron,
            "timezone": routine.timezone,
            "require_approval": routine.require_approval,
            "definition_version": routine.definition_version,
            "steps": steps,
        }

    def ensure_automation_run(
        self,
        routine: Routine,
        *,
        trigger_kind: str,
        trigger_event_id: str,
        idempotency_key: str,
    ) -> AutomationRun:
        with self._conn() as conn:
            existing = conn.execute(
                "SELECT * FROM automation_runs WHERE idempotency_key = %s",
                (idempotency_key,),
            ).fetchone()
            auto = conn.execute(
                "SELECT id FROM automations WHERE routine_id = %s",
                (routine.id,),
            ).fetchone()
            conn.commit()
        if existing is not None:
            return self._automation_run_from_row(existing)
        if auto is None:
            self.upsert_automation_from_routine(routine)
        snapshot = self.automation_snapshot(routine)
        state = "waiting_for_approval" if routine.require_approval else "queued"
        run_id = new_id("arun")
        now = isoformat_utc()
        with self._conn() as conn:
            auto = conn.execute(
                "SELECT id FROM automations WHERE routine_id = %s",
                (routine.id,),
            ).fetchone()
            if auto is None:
                conn.commit()
                raise RuntimeError("automation missing")
            row = conn.execute(
                """
                INSERT INTO automation_runs (
                    id, automation_id, routine_id, definition_version, trigger_kind,
                    trigger_event_id, idempotency_key, state, snapshot, created_at, updated_at
                ) VALUES (
                    %s, %s, %s, %s, %s,
                    %s, %s, %s, %s::jsonb, %s, %s
                )
                ON CONFLICT (idempotency_key) DO NOTHING
                RETURNING *
                """,
                (
                    run_id,
                    str(auto["id"]),
                    routine.id,
                    routine.definition_version,
                    trigger_kind,
                    trigger_event_id,
                    idempotency_key,
                    state,
                    json.dumps(snapshot),
                    now,
                    now,
                ),
            ).fetchone()
            if row is None:
                row = conn.execute(
                    "SELECT * FROM automation_runs WHERE idempotency_key = %s",
                    (idempotency_key,),
                ).fetchone()
            else:
                seq = 1
                if routine.require_approval:
                    conn.execute(
                        """
                        INSERT INTO automation_step_runs (
                            id, automation_run_id, seq, kind, state
                        ) VALUES (%s, %s, %s, 'wait_approval', 'waiting')
                        """,
                        (new_id("asrun"), run_id, seq),
                    )
                    seq += 1
                conn.execute(
                    """
                    INSERT INTO automation_step_runs (
                        id, automation_run_id, seq, kind, state
                    ) VALUES (%s, %s, %s, 'prompt_bot', 'pending')
                    """,
                    (new_id("asrun"), run_id, seq),
                )
                self._append_activity_tx(
                    conn,
                    "automation.run",
                    "host",
                    routine.id,
                    {"id": run_id, "state": state, "trigger_kind": trigger_kind},
                    None,
                    1,
                )
            conn.commit()
        if row is None:
            raise RuntimeError("automation run missing")
        return self._automation_run_from_row(row)

    def list_automation_runs(self, routine_id: str, *, limit: int = 20) -> list[AutomationRun]:
        cap = max(1, min(int(limit), 50))
        with self._conn() as conn:
            rows = conn.execute(
                """
                SELECT * FROM automation_runs
                WHERE routine_id = %s
                ORDER BY created_at DESC
                LIMIT %s
                """,
                (routine_id, cap),
            ).fetchall()
            conn.commit()
        return [self._automation_run_from_row(row) for row in rows]

    def get_automation_run(self, run_id: str) -> AutomationRun | None:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM automation_runs WHERE id = %s",
                (run_id,),
            ).fetchone()
            conn.commit()
        return self._automation_run_from_row(row) if row else None

    def ensure_approval_ask(self, bot: Bot, auto_run: AutomationRun) -> AutomationRun:
        snapshot = auto_run.snapshot
        if not snapshot.get("require_approval"):
            return auto_run
        if auto_run.snapshot.get("approval_posted") or auto_run.state != "waiting_for_approval":
            current = self.get_automation_run(auto_run.id)
            return current or auto_run
        if self.has_active_run(bot.id):
            return auto_run
        run = self.begin_run(bot, trigger="routine")
        question = f"Approve routine {snapshot.get('name') or 'this routine'}?"
        blocks = [
            {
                "kind": "ask",
                "text": question,
                "detail": str(snapshot.get("prompt") or "")[:280],
                "status": "pending",
                "automation_run_id": auto_run.id,
                "actions": [
                    {"id": "opt_1", "label": APPROVE_LABEL},
                    {"id": "opt_2", "label": DENY_LABEL},
                ],
            }
        ]
        message = self.append_bot_message(bot, blocks, run_id=run.id)
        self.mark_run_waiting_input(run.id)
        now = isoformat_utc()
        with self._conn() as conn:
            conn.execute(
                """
                UPDATE automation_runs
                SET approval_run_id = %s, updated_at = %s,
                    snapshot = snapshot || %s::jsonb
                WHERE id = %s
                """,
                (
                    run.id,
                    now,
                    json.dumps({"approval_posted": True, "approval_message_id": message.id}),
                    auto_run.id,
                ),
            )
            conn.commit()
        found = self.get_automation_run(auto_run.id)
        return found or auto_run

    def answer_automation_ask(
        self,
        bot_id: str,
        run_id: str,
        message_id: str,
        answer: str,
    ) -> tuple[Any, AutomationRun] | None:
        text = (answer or "").strip()
        if not text:
            return None
        with self._conn() as conn:
            row = conn.execute(
                """
                SELECT m.id, m.blocks, m.run_id, ar.id AS automation_run_id, ar.state
                FROM messages m
                JOIN automation_runs ar ON ar.approval_run_id = m.run_id
                WHERE m.id = %s AND m.run_id = %s AND ar.state = 'waiting_for_approval'
                """,
                (message_id, run_id),
            ).fetchone()
            conn.commit()
        if row is None:
            return None
        updated = self.answer_message_ask(message_id, text)
        if updated is None:
            return None
        approved = text.strip().lower() == APPROVE_LABEL.lower()
        now = isoformat_utc()
        with self._conn() as conn:
            conn.execute(
                """
                UPDATE runs
                SET status = %s, completed_at = %s
                WHERE id = %s
                """,
                (
                    RunStatus.completed.value if approved else RunStatus.cancelled.value,
                    now,
                    run_id,
                ),
            )
            conn.execute(
                "UPDATE bots SET status = 'idle', updated_at = %s WHERE id = %s",
                (now, bot_id),
            )
            if approved:
                conn.execute(
                    """
                    UPDATE automation_runs
                    SET state = 'queued', updated_at = %s
                    WHERE id = %s
                    """,
                    (now, row["automation_run_id"]),
                )
                conn.execute(
                    """
                    UPDATE automation_step_runs
                    SET state = 'succeeded', updated_at = now()
                    WHERE automation_run_id = %s AND kind = 'wait_approval'
                    """,
                    (row["automation_run_id"],),
                )
            else:
                conn.execute(
                    """
                    UPDATE automation_runs
                    SET state = 'cancelled', error = 'denied', updated_at = %s, completed_at = %s
                    WHERE id = %s
                    """,
                    (now, now, row["automation_run_id"]),
                )
                conn.execute(
                    """
                    UPDATE automation_step_runs
                    SET state = 'failed', error_code = 'denied', updated_at = now()
                    WHERE automation_run_id = %s AND kind = 'wait_approval'
                    """,
                    (row["automation_run_id"]),
                )
            self._append_activity_tx(
                conn,
                "automation.run",
                "owner",
                str(row["automation_run_id"]),
                {"state": "queued" if approved else "cancelled", "answer": text[:80]},
                None,
                1,
            )
            conn.commit()
        auto = self.get_automation_run(str(row["automation_run_id"]))
        if auto is None:
            return None
        return updated, auto

    def enqueue_automation_prompt(self, auto_run: AutomationRun) -> None:
        snapshot = auto_run.snapshot
        self.enqueue_job(
            job_type="routine.fire",
            resource_id=auto_run.routine_id,
            idempotency_key=f"fire:{auto_run.id}",
            payload={
                "version": 1,
                "routine_id": auto_run.routine_id,
                "bot_id": str(snapshot.get("bot_id") or ""),
                "prompt": str(snapshot.get("prompt") or ""),
                "automation_run_id": auto_run.id,
            },
            max_attempts=5,
        )
        if auto_run.state == "queued":
            self.finish_automation_run(auto_run.id, state="running")

    def finish_automation_run(
        self,
        run_id: str,
        *,
        state: str,
        error: str | None = None,
        thread_run_id: str | None = None,
        error_code: str | None = None,
    ) -> None:
        now = isoformat_utc()
        terminal = state in {"succeeded", "failed", "cancelled"}
        with self._conn() as conn:
            conn.execute(
                """
                UPDATE automation_runs
                SET state = %s, error = %s, thread_run_id = COALESCE(%s, thread_run_id),
                    updated_at = %s, completed_at = CASE WHEN %s THEN %s ELSE completed_at END
                WHERE id = %s
                """,
                (state, error, thread_run_id, now, terminal, now, run_id),
            )
            if error_code or state in {"succeeded", "failed"}:
                step_state = "succeeded" if state == "succeeded" else "failed"
                conn.execute(
                    """
                    UPDATE automation_step_runs
                    SET state = %s, error_code = %s, updated_at = now()
                    WHERE automation_run_id = %s AND kind = 'prompt_bot'
                    """,
                    (step_state, error_code, run_id),
                )
            conn.commit()

    def _fail_automation_run(self, run_id: str, error_code: str) -> None:
        self.finish_automation_run(run_id, state="failed", error=error_code, error_code=error_code)

    def _automation_run_from_row(self, row: dict[str, Any]) -> AutomationRun:
        raw = row["snapshot"]
        if isinstance(raw, str):
            snapshot = json.loads(raw)
        else:
            snapshot = dict(raw or {})
        return AutomationRun(
            id=str(row["id"]),
            automation_id=str(row["automation_id"]),
            routine_id=str(row["routine_id"]),
            definition_version=int(row["definition_version"]),
            trigger_kind=str(row["trigger_kind"]),
            trigger_event_id=str(row["trigger_event_id"]),
            state=row["state"],
            snapshot=snapshot,
            thread_run_id=str(row["thread_run_id"]) if row.get("thread_run_id") else None,
            error=str(row["error"]) if row.get("error") else None,
            created_at=parse_iso(row["created_at"]),
            updated_at=parse_iso(row["updated_at"]),
        )
