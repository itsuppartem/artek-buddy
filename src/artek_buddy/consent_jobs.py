"""Owner-job claim, file, and result transport. Card Allow/Deny stays on ConsentHub."""

from __future__ import annotations

import logging
import secrets
import threading
from typing import Any

from artek_buddy.consent import (
    CLASS_OWNER_READ,
    OWNER_CLASSES,
    OWNER_FILE_WAIT,
    OWNER_RESULT_WAIT,
    owner_scope,
)
from artek_buddy.contracts.events import ProductEventType
from artek_buddy.db.shaping import new_id

log = logging.getLogger("artek_buddy")


class OwnerJobTransport:
    """Claim, deliver, and wait for This-PC jobs. No ask-card posting."""

    def cancel_owner_jobs(self, run_ids: list[str]) -> None:
        wanted = [item for item in run_ids if item]
        if not wanted:
            return
        finder = getattr(self.store, "owner_job_ids_for_runs", None)
        request_ids: list[str] = []
        if callable(finder):
            try:
                request_ids = list(finder(wanted) or [])
            except Exception:
                log.exception("failed to list owner jobs for cancel")
                request_ids = []
        payload = {"ok": False, "error": "Stopped."}
        for request_id in request_ids:
            try:
                self.store.finish_consent_job(request_id, "failed")
            except Exception:
                log.exception("failed to finish owner job on cancel")
            with self._lock:
                self._results[request_id] = dict(payload)
                waiter = self._result_waiters.get(request_id)
                file_waiter = self._file_waiters.get(request_id)
            if waiter is not None:
                waiter.set()
            if file_waiter is not None:
                file_waiter.set()

    def get_job(self, request_id: str) -> dict[str, Any] | None:
        row = self.store.get_consent_request(request_id)
        if row is None:
            return None
        job = dict(self._jobs.get(request_id) or {})
        job.setdefault("id", request_id)
        job.setdefault("action_class", row.action_class)
        job.setdefault("scope_key", row.scope_key)
        job.setdefault("summary", row.summary)
        job.setdefault("status", row.status)
        job.setdefault("job_status", row.job_status)
        return job

    def acknowledge_owner_job(self, request_id: str) -> bool:
        claimed, _claim = self.claim_owner_job(request_id)
        return claimed

    def claim_owner_job(
        self,
        request_id: str,
        *,
        claim_capable: bool = False,
    ) -> tuple[bool, str | None]:
        row = self.store.get_consent_request(request_id)
        if row is None or row.action_class not in OWNER_CLASSES or row.job_status != "queued":
            return False, None
        with self._lock:
            if not self.store.acknowledge_consent_job(request_id):
                return False, None
            claim = secrets.token_urlsafe(24) if claim_capable else None
            if claim is not None:
                self._job_claims[request_id] = claim
        return True, claim

    def put_owner_file(
        self,
        request_id: str,
        name: str,
        data: bytes,
        *,
        claim: str | None = None,
    ) -> bool:
        row = self.store.get_consent_request(request_id)
        if (
            row is None
            or row.action_class != CLASS_OWNER_READ
            or row.job_status not in {"queued", "acknowledged"}
            or not self._owner_claim_matches(request_id, claim)
        ):
            return False
        with self._lock:
            self._files[request_id] = (name, data)
            waiter = self._file_waiters.get(request_id)
        if waiter is not None:
            waiter.set()
        return True

    def put_owner_result(
        self,
        request_id: str,
        payload: dict[str, Any],
        *,
        claim: str | None = None,
    ) -> bool:
        row = self.store.get_consent_request(request_id)
        if (
            row is None
            or row.action_class not in OWNER_CLASSES
            or row.job_status not in {"queued", "acknowledged"}
            or not self._owner_claim_matches(request_id, claim)
        ):
            return False
        final_status = "completed" if payload.get("ok", True) else "failed"
        if not self.store.finish_consent_job(request_id, final_status):
            return False
        with self._lock:
            self._job_claims.pop(request_id, None)
            self._results[request_id] = dict(payload)
            waiter = self._result_waiters.get(request_id)
            file_waiter = self._file_waiters.get(request_id)
        if waiter is not None:
            waiter.set()
        if file_waiter is not None:
            file_waiter.set()
        return True

    def _owner_claim_matches(self, request_id: str, claim: str | None) -> bool:
        with self._lock:
            expected = self._job_claims.get(request_id)
        if expected is None:
            return True
        if not claim:
            return False
        return secrets.compare_digest(expected, claim)

    def take_owner_result(
        self,
        request_id: str | None,
        *,
        finalize_timeout: bool = True,
    ) -> dict[str, Any] | None:
        if not request_id:
            return None
        waiter = threading.Event()
        with self._lock:
            if request_id in self._results:
                return self._results.pop(request_id)
            self._result_waiters[request_id] = waiter
        waiter.wait(OWNER_RESULT_WAIT)
        with self._lock:
            self._result_waiters.pop(request_id, None)
            found = self._results.pop(request_id, None)
        if found is None and finalize_timeout:
            self.timeout_owner_job(request_id)
        return found

    def timeout_owner_job(self, request_id: str | None) -> bool:
        if not request_id:
            return False
        finished = bool(self.store.finish_consent_job(request_id, "timed_out"))
        if finished:
            with self._lock:
                self._job_claims.pop(request_id, None)
        return finished

    def pull_owner_action(
        self,
        *,
        bot_id: str,
        action_class: str,
        scope_key: str,
        summary: str,
        job: dict[str, Any],
        run_id: str | None,
        device_id: str | None,
    ) -> dict[str, Any] | None:
        _ = device_id
        bot = self.store.get_bot(bot_id)
        if bot is None:
            return None
        request_id = new_id("cns")
        self._jobs[request_id] = {**job, "action_class": action_class, "scope_key": scope_key}
        self.store.create_consent_request(
            request_id,
            bot_id=bot_id,
            run_id=run_id,
            parent_run_id=self._parent_run_id(run_id),
            thread_id=bot.thread_id,
            message_id=None,
            action_class=action_class,
            scope_key=scope_key,
            summary=summary,
            workspace_id=bot.workspace_id,
            job_status="queued",
        )
        if run_id:
            try:
                self.store.mark_run_waiting_input(run_id)
            except Exception:
                log.exception("failed to mark waiting_input")
        payload: dict[str, Any] = {
            "run_id": run_id,
            "consent_id": request_id,
            "text": summary,
            "action_class": action_class,
            "auto": True,
        }
        for field in ("path", "command", "cwd", "kind"):
            if job.get(field):
                payload[field] = job[field]
        self._publish(bot, ProductEventType.RUN_WAITING_INPUT, payload, run_id)
        found = self.take_owner_result(request_id, finalize_timeout=False)
        if found is None and action_class == CLASS_OWNER_READ and job.get("kind") != "list":
            file_found = self.take_owner_file(request_id, finalize_timeout=False)
            if file_found is not None:
                name, data = file_found
                found = {"ok": True, "name": name, "bytes": len(data), "_data": data}
        if found is None:
            self.timeout_owner_job(request_id)
        if run_id:
            try:
                self.store.mark_run_running(run_id)
            except Exception:
                log.exception("failed to resume run after owner action")
        return found

    def pull_owner_file(
        self,
        *,
        bot_id: str,
        path: str,
        run_id: str | None,
        device_id: str | None,
    ) -> tuple[str, bytes] | None:
        """Always-grant path: no card, ask the paired client to send the file."""
        request_id = self.start_auto_owner_read(
            bot_id=bot_id,
            path=path,
            run_id=run_id,
            device_id=device_id,
        )
        if not request_id:
            return None
        found = self.take_owner_file(request_id)
        if run_id:
            try:
                self.store.mark_run_running(run_id)
            except Exception:
                log.exception("failed to resume run after owner file")
        return found

    def start_auto_owner_read(
        self,
        *,
        bot_id: str,
        path: str,
        run_id: str | None,
        device_id: str | None,
    ) -> str | None:
        """Publish the auto job on the caller’s thread (the event loop). Wait separately."""
        _ = device_id
        bot = self.store.get_bot(bot_id)
        if bot is None:
            return None
        request_id = new_id("cns")
        self._jobs[request_id] = {
            "action_class": CLASS_OWNER_READ,
            "path": path,
            "kind": "read",
        }
        self.store.create_consent_request(
            request_id,
            bot_id=bot_id,
            run_id=run_id,
            parent_run_id=self._parent_run_id(run_id),
            thread_id=bot.thread_id,
            message_id=None,
            action_class=CLASS_OWNER_READ,
            scope_key=owner_scope(path),
            summary=f"Read {path} from your computer?",
            workspace_id=bot.workspace_id,
            job_status="queued",
        )
        if run_id:
            try:
                self.store.mark_run_waiting_input(run_id)
            except Exception:
                log.exception("failed to mark waiting_input")
        self._publish(
            bot,
            ProductEventType.RUN_WAITING_INPUT,
            {
                "run_id": run_id,
                "consent_id": request_id,
                "text": f"Read {path} from your computer?",
                "action_class": CLASS_OWNER_READ,
                "path": path,
                "auto": True,
            },
            run_id,
        )
        return request_id

    def take_owner_file(
        self,
        request_id: str | None,
        *,
        finalize_timeout: bool = True,
    ) -> tuple[str, bytes] | None:
        if not request_id:
            return None
        waiter = threading.Event()
        with self._lock:
            if request_id in self._files:
                return self._files.pop(request_id)
            if request_id in self._results:
                return None
            self._file_waiters[request_id] = waiter
        waiter.wait(OWNER_FILE_WAIT)
        with self._lock:
            self._file_waiters.pop(request_id, None)
            found = self._files.pop(request_id, None)
        if found is None and finalize_timeout:
            self.timeout_owner_job(request_id)
        return found
