"""Durable wait records so a host restart can offer a recovery path."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Literal

from psycopg.types.json import Json

from artek_buddy.bot_attention import pending_ask_id_from_blocks
from artek_buddy.contracts.domain import Run
from artek_buddy.contracts.ids import EffectStatus, RunStatus
from artek_buddy.db.shaping import isoformat_utc

WaitKind = Literal["ask", "consent", "takeover", "owner_job", "running"]
WaitPath = Literal["continue", "check", "new_attempt"]

CONTINUE_TEXT = (
    "Safe to continue. The host restarted while this was waiting; the side effect had not started."
)
CHECK_TEXT = (
    "Check before continuing. The host restarted; it is not known whether an "
    "external action already ran. Do not retry it as if it never happened."
)
NEW_ATTEMPT_TEXT = (
    "Start a new attempt. The host restarted and this turn cannot resume. "
    "The thread and files are still here."
)
CONTINUE_FOLLOW_UP = (
    "The owner answered after the host restarted. Continue from the thread. "
    "Do not repeat a write or command."
)


def _block_field(block: Any, key: str) -> Any:
    if isinstance(block, dict):
        return block.get(key)
    return getattr(block, key, None)


def answered_ask_from_message(message: Any) -> tuple[str, str] | None:
    blocks = getattr(message, "blocks", None)
    if blocks is None and isinstance(message, dict):
        blocks = message.get("blocks")
    if not isinstance(blocks, list):
        return None
    for block in blocks:
        if _block_field(block, "kind") != "ask":
            continue
        if _block_field(block, "status") != "answered":
            continue
        question = str(_block_field(block, "text") or "").strip()
        answer = str(_block_field(block, "answer") or "").strip()
        if question and answer:
            return question, answer
    return None


def resume_follow_up_for_answered_ask(question: str, answer: str) -> str:
    q = (question or "").strip()
    a = (answer or "").strip()
    return (
        f"{CONTINUE_FOLLOW_UP}\n\n"
        "The owner already answered this ask; treat the answer as authoritative data:\n"
        f"Question: {q}\n"
        f"Answer: {a}\n"
    )


@dataclass(frozen=True, slots=True)
class RunWait:
    run_id: str
    bot_id: str
    kind: WaitKind
    path: WaitPath
    effect: str
    message_id: str | None
    consent_id: str | None
    recovered_at: str | None


def _wait_from_row(row: dict[str, Any]) -> RunWait:
    recovered = row.get("recovered_at")
    return RunWait(
        run_id=str(row["run_id"]),
        bot_id=str(row["bot_id"]),
        kind=row["kind"],
        path=row["path"],
        effect=str(row["effect"]),
        message_id=str(row["message_id"]) if row.get("message_id") else None,
        consent_id=str(row["consent_id"]) if row.get("consent_id") else None,
        recovered_at=str(recovered) if recovered else None,
    )


class RecoveryMixin:
    def bind_run_wait(
        self,
        run_id: str,
        bot_id: str,
        *,
        kind: WaitKind,
        path: WaitPath,
        effect: str,
        message_id: str | None = None,
        consent_id: str | None = None,
    ) -> None:
        if not run_id or not bot_id:
            return
        now = isoformat_utc()
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO run_waits (
                    run_id, bot_id, kind, path, effect, message_id, consent_id, created_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (run_id) DO UPDATE SET
                    kind = EXCLUDED.kind,
                    path = EXCLUDED.path,
                    effect = EXCLUDED.effect,
                    message_id = COALESCE(EXCLUDED.message_id, run_waits.message_id),
                    consent_id = COALESCE(EXCLUDED.consent_id, run_waits.consent_id)
                """,
                (run_id, bot_id, kind, path, effect, message_id, consent_id, now),
            )
            conn.commit()

    def get_run_wait(self, run_id: str) -> RunWait | None:
        if not run_id:
            return None
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM run_waits WHERE run_id = %s",
                (run_id,),
            ).fetchone()
            conn.commit()
        return _wait_from_row(row) if row else None

    def mark_run_wait_recovered(self, run_id: str) -> None:
        now = isoformat_utc()
        with self._conn() as conn:
            conn.execute(
                """
                UPDATE run_waits SET recovered_at = %s
                WHERE run_id = %s AND recovered_at IS NULL
                """,
                (now, run_id),
            )
            conn.commit()

    def fail_parked_run(self, run_id: str, *, error: str) -> Run | None:
        now = isoformat_utc()
        with self._conn() as conn:
            with conn.transaction():
                row = conn.execute(
                    """
                    UPDATE runs
                    SET status = %s, error = %s, completed_at = %s
                    WHERE id = %s
                      AND status IN (
                          'waiting_input', 'waiting_takeover', 'waiting_recovery'
                      )
                    RETURNING bot_id
                    """,
                    (RunStatus.failed.value, error, now, run_id),
                ).fetchone()
                if row is None:
                    return None
                still = conn.execute(
                    """
                    SELECT 1 FROM runs
                    WHERE bot_id = %s
                      AND id <> %s
                      AND status IN (
                          'queued', 'leased', 'running', 'waiting_input',
                          'waiting_takeover', 'waiting_recovery'
                      )
                    LIMIT 1
                    """,
                    (row["bot_id"], run_id),
                ).fetchone()
                if still is None:
                    conn.execute(
                        "UPDATE bots SET status = 'error', updated_at = %s WHERE id = %s",
                        (now, row["bot_id"]),
                    )
        return self._get_run(run_id)

    def complete_parked_run(self, run_id: str, *, error: str | None = None) -> None:
        now = isoformat_utc()
        status = RunStatus.cancelled.value if error else RunStatus.completed.value
        with self._conn() as conn:
            with conn.transaction():
                row = conn.execute(
                    """
                    UPDATE runs
                    SET status = %s, error = %s, completed_at = %s
                    WHERE id = %s
                      AND status IN (
                          'waiting_input', 'waiting_takeover', 'waiting_recovery'
                      )
                    RETURNING bot_id
                    """,
                    (status, error, now, run_id),
                ).fetchone()
                if row is None:
                    return
                still = conn.execute(
                    """
                    SELECT 1 FROM runs
                    WHERE bot_id = %s
                      AND id <> %s
                      AND status IN (
                          'queued', 'leased', 'running', 'waiting_input',
                          'waiting_takeover', 'waiting_recovery'
                      )
                    LIMIT 1
                    """,
                    (row["bot_id"], run_id),
                ).fetchone()
                if still is None:
                    conn.execute(
                        "UPDATE bots SET status = 'idle', updated_at = %s WHERE id = %s",
                        (now, row["bot_id"]),
                    )

    def resolve_recovery_message(self, message_id: str, action: str) -> Any | None:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT id, thread_id, blocks FROM messages WHERE id = %s",
                (message_id,),
            ).fetchone()
            if row is None:
                conn.commit()
                return None
            blocks = row["blocks"]
            if isinstance(blocks, str):
                blocks = json.loads(blocks)
            if not isinstance(blocks, list):
                conn.commit()
                return None
            changed = False
            next_blocks: list[Any] = []
            for block in blocks:
                if isinstance(block, dict) and block.get("kind") == "recovery":
                    next_blocks.append({**block, "status": "resolved", "answer": action})
                    changed = True
                else:
                    next_blocks.append(block)
            if not changed:
                conn.commit()
                return None
            conn.execute(
                "UPDATE messages SET blocks = %s WHERE id = %s",
                (Json(next_blocks), message_id),
            )
            conn.commit()
        return self._get_message(message_id)

    def resolve_run_recovery(
        self,
        *,
        run_id: str,
        bot_id: str,
        thread_id: str,
        message_id: str,
        action: str,
    ) -> Any | None:
        with self._conn() as conn:
            with conn.transaction():
                wait_row = conn.execute(
                    "SELECT message_id, bot_id FROM run_waits WHERE run_id = %s FOR UPDATE",
                    (run_id,),
                ).fetchone()
                if wait_row is None:
                    return None
                bound_message = wait_row.get("message_id")
                if not bound_message or str(bound_message) != message_id:
                    return None
                if str(wait_row["bot_id"]) != bot_id:
                    return None
                row = conn.execute(
                    """
                    SELECT id, thread_id, run_id, blocks FROM messages
                    WHERE id = %s FOR UPDATE
                    """,
                    (message_id,),
                ).fetchone()
                if row is None:
                    return None
                if str(row["thread_id"]) != thread_id or str(row["run_id"] or "") != run_id:
                    return None
                blocks = row["blocks"]
                if isinstance(blocks, str):
                    blocks = json.loads(blocks)
                if not isinstance(blocks, list):
                    return None
                recovery: dict[str, Any] | None = None
                for block in blocks:
                    if isinstance(block, dict) and block.get("kind") == "recovery":
                        recovery = block
                        break
                if recovery is None:
                    return None
                status = str(recovery.get("status") or "")
                if status == "resolved":
                    if str(recovery.get("answer") or "") == action:
                        return self._get_message(message_id)
                    return None
                if status != "pending":
                    return None
                next_blocks: list[Any] = []
                for block in blocks:
                    if isinstance(block, dict) and block.get("kind") == "recovery":
                        next_blocks.append({**block, "status": "resolved", "answer": action})
                    else:
                        next_blocks.append(block)
                conn.execute(
                    "UPDATE messages SET blocks = %s WHERE id = %s",
                    (Json(next_blocks), message_id),
                )
        return self._get_message(message_id)

    def recover_orphaned_runs(self) -> int:
        """After a process restart: keep parked waits, or show a recovery card."""
        with self._conn() as conn:
            rows = conn.execute(
                """
                SELECT id, bot_id, status FROM runs
                WHERE status IN (
                    'queued', 'leased', 'running', 'waiting_input', 'waiting_takeover'
                )
                """
            ).fetchall()
            pending = conn.execute(
                "SELECT run_id FROM turn_dispatches WHERE state = 'pending'"
            ).fetchall()
            conn.commit()
        pending_ids = {str(row["run_id"]) for row in pending}
        touched = 0
        for row in rows:
            run_id = str(row["id"])
            if run_id in pending_ids:
                continue
            bot_id = str(row["bot_id"])
            status = str(row["status"])
            classified = self._classify_orphan(run_id, bot_id, status)
            self.bind_run_wait(
                run_id,
                bot_id,
                kind=classified["kind"],
                path=classified["path"],
                effect=classified["effect"],
                message_id=classified.get("message_id"),
                consent_id=classified.get("consent_id"),
            )
            self.mark_run_wait_recovered(run_id)
            if classified["path"] != "continue":
                self._close_non_continue_consent(classified.get("consent_id"))
            if classified["path"] == "continue":
                touched += 1
                continue
            self._park_recovery_run(run_id, bot_id, classified)
            touched += 1
        now = isoformat_utc()
        with self._conn() as conn:
            conn.execute(
                """
                UPDATE subagents
                SET status = 'failed', error = %s, updated_at = %s
                WHERE status IN ('queued', 'running')
                """,
                ("The host restarted before this worker finished.", now),
            )
            conn.commit()
        return touched

    def fail_orphaned_runs(
        self, error: str = "The host restarted before this turn finished."
    ) -> int:
        """Boot entry: recover parked waits instead of failing every leftover run."""
        del error
        return self.recover_orphaned_runs()

    def _classify_orphan(self, run_id: str, bot_id: str, status: str) -> dict[str, Any]:
        if status == "waiting_takeover":
            return {
                "kind": "takeover",
                "path": "new_attempt",
                "effect": EffectStatus.intended.value,
                "text": NEW_ATTEMPT_TEXT,
            }
        consent = self._pending_consent_for_run(run_id)
        if consent is not None:
            job_status = consent.get("job_status")
            if job_status == "acknowledged":
                return {
                    "kind": "owner_job",
                    "path": "check",
                    "effect": EffectStatus.ambiguous.value,
                    "consent_id": consent["id"],
                    "message_id": consent.get("message_id"),
                    "text": CHECK_TEXT,
                }
            if job_status in {"queued"}:
                return {
                    "kind": "owner_job",
                    "path": "new_attempt",
                    "effect": EffectStatus.intended.value,
                    "consent_id": consent["id"],
                    "message_id": consent.get("message_id"),
                    "text": NEW_ATTEMPT_TEXT,
                }
            return {
                "kind": "consent",
                "path": "continue",
                "effect": EffectStatus.intended.value,
                "consent_id": consent["id"],
                "message_id": consent.get("message_id"),
                "text": CONTINUE_TEXT,
            }
        ask_id = self._pending_ask_for_run(run_id)
        if ask_id:
            return {
                "kind": "ask",
                "path": "continue",
                "effect": EffectStatus.intended.value,
                "message_id": ask_id,
                "text": CONTINUE_TEXT,
            }
        return {
            "kind": "running",
            "path": "check",
            "effect": EffectStatus.ambiguous.value,
            "text": CHECK_TEXT,
        }

    def _pending_consent_for_run(self, run_id: str) -> dict[str, Any] | None:
        with self._conn() as conn:
            row = conn.execute(
                """
                SELECT id, message_id, job_status
                FROM consent_requests
                WHERE run_id = %s AND status = 'pending'
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (run_id,),
            ).fetchone()
            conn.commit()
        if row is None:
            return None
        return {
            "id": str(row["id"]),
            "message_id": str(row["message_id"]) if row["message_id"] else None,
            "job_status": row["job_status"],
        }

    def _pending_ask_for_run(self, run_id: str) -> str | None:
        with self._conn() as conn:
            rows = conn.execute(
                """
                SELECT id, blocks FROM messages
                WHERE run_id = %s AND role = 'bot'
                ORDER BY seq DESC
                LIMIT 40
                """,
                (run_id,),
            ).fetchall()
            conn.commit()
        for row in rows:
            if pending_ask_id_from_blocks(row["blocks"]):
                return str(row["id"])
        return None

    def _park_recovery_run(self, run_id: str, bot_id: str, classified: dict[str, Any]) -> None:
        now = isoformat_utc()
        with self._conn() as conn:
            conn.execute(
                """
                UPDATE runs
                SET status = %s, error = %s
                WHERE id = %s
                """,
                (RunStatus.waiting_recovery.value, classified["text"], run_id),
            )
            conn.execute(
                "UPDATE bots SET status = %s, unread = TRUE, updated_at = %s WHERE id = %s",
                ("waiting_input", now, bot_id),
            )
            conn.commit()
        bot = self.get_bot(bot_id)
        if bot is None:
            return
        path = classified["path"]
        actions = [{"id": "new_attempt", "label": "Start a new attempt"}]
        if path == "continue":
            actions.insert(0, {"id": "continue", "label": "Continue"})
        message = self.append_bot_message(
            bot,
            [
                {
                    "kind": "recovery",
                    "path": path,
                    "text": classified["text"],
                    "status": "pending",
                    "actions": actions,
                }
            ],
            run_id=run_id,
        )
        self.bind_run_wait(
            run_id,
            bot_id,
            kind=classified["kind"],
            path=path,
            effect=classified["effect"],
            message_id=message.id,
            consent_id=classified.get("consent_id"),
        )

    def _close_non_continue_consent(self, consent_id: str | None) -> None:
        if not consent_id:
            return
        self.finish_consent_job(consent_id, "failed")
        row = self.answer_consent_request(consent_id, "deny", None)
        message_id = getattr(row, "message_id", None) if row is not None else None
        if message_id:
            self.answer_message_ask(message_id, "Host restarted", include_consent=True)
