from __future__ import annotations

import json
import logging
import os
import time
import urllib.error
import urllib.request

from artek_buddy.db import DatabaseUnavailable
from artek_buddy.db.history import HistoryStore
from artek_buddy.observe import configure_logging, mint_request_id

log = logging.getLogger("artek_buddy.worker")

DEFAULT_POLL_SECONDS = 15
DEFAULT_CONCURRENCY = 4
RETRY_SECONDS = 60


def host_base() -> str:
    port = os.environ.get("HTTP_PORT", "8080").strip() or "8080"
    return f"http://127.0.0.1:{port}"


def wake_routine(
    base: str,
    token: str,
    bot_id: str,
    prompt: str,
    timeout: float = 30,
    *,
    job_id: str | None = None,
) -> int:
    request_id = mint_request_id()
    payload: dict[str, str] = {"text": prompt, "trigger": "routine"}
    if job_id:
        payload["idempotency_key"] = job_id
    request = urllib.request.Request(
        f"{base.rstrip('/')}/v1/threads/{bot_id}/messages",
        data=json.dumps(payload).encode("utf-8"),
        method="POST",
        headers={
            "Accept": "application/json",
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "X-Request-Id": request_id,
        },
    )
    log.info("routine wake bot=%s request_id=%s", bot_id, request_id)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as resp:
            return int(resp.status)
    except urllib.error.HTTPError as err:
        return int(err.code)
    except OSError:
        return 0


def stop_computer(base: str, token: str, bot_id: str, timeout: float = 30) -> int:
    request = urllib.request.Request(
        f"{base.rstrip('/')}/v1/computer/{bot_id}/stop",
        data=b"{}",
        method="POST",
        headers={
            "Accept": "application/json",
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as resp:
            return int(resp.status)
    except urllib.error.HTTPError as err:
        return int(err.code)
    except OSError:
        return 0


def run_once(store: HistoryStore, base: str, token: str) -> int:
    # 1. Enqueue due routines as durable jobs
    due = store.claim_due_routines()
    for routine in due:
        idempotency_key = f"routine:{routine.id}:{routine.last_run_at}"
        auto_run = store.ensure_automation_run(
            routine,
            trigger_kind="cron",
            trigger_event_id=str(routine.last_run_at or ""),
            idempotency_key=idempotency_key,
        )
        if auto_run.state == "waiting_for_approval":
            bot = store.get_bot(routine.bot_id)
            if bot is None:
                store.finish_automation_run(
                    auto_run.id, state="failed", error="bot_gone", error_code="bot_gone"
                )
            else:
                store.ensure_approval_ask(bot, auto_run)
        elif auto_run.state == "queued":
            store.enqueue_automation_prompt(auto_run)
        store.ack_routine(routine.id)

    # 2. Claim and execute durable jobs (bounded concurrency for Pi)
    concurrency = int(
        os.environ.get("WORKER_CONCURRENCY", str(DEFAULT_CONCURRENCY)) or str(DEFAULT_CONCURRENCY)
    )
    worker_id = f"worker_{os.getpid()}"
    claimed_jobs = store.claim_jobs(worker_id=worker_id, limit=concurrency)
    woke = 0

    for job in claimed_jobs:
        if job.job_type == "routine.fire":
            bot_id = str(job.payload.get("bot_id") or "")
            prompt = str(job.payload.get("prompt") or "")
            status = wake_routine(base, token, bot_id, prompt, job_id=job.id)
            auto_run_id = str(job.payload.get("automation_run_id") or "")
            if status in {200, 201}:
                store.ack_job(job.id, result={"status": status})
                if auto_run_id:
                    store.finish_automation_run(auto_run_id, state="succeeded")
                woke += 1
                log.info("routine job succeeded id=%s status=%s", job.id, status)
            elif status == 409:
                store.ack_job(job.id, result={"status": status, "skipped": "busy"})
                if auto_run_id:
                    store.finish_automation_run(
                        auto_run_id, state="failed", error="bot_busy", error_code="bot_busy"
                    )
                log.info("routine job skipped busy id=%s", job.id)
            elif status == 404:
                store.fail_job(job.id, error=f"HTTP {status}")
                if auto_run_id:
                    store.finish_automation_run(
                        auto_run_id, state="failed", error="bot_gone", error_code="bot_gone"
                    )
                log.warning("routine job failed id=%s status=%s", job.id, status)
            else:
                store.fail_job(job.id, error=f"HTTP {status}")
                if auto_run_id:
                    store.finish_automation_run(
                        auto_run_id,
                        state="failed",
                        error=f"HTTP {status}",
                        error_code="wake_failed",
                    )
                log.warning("routine job failed id=%s status=%s", job.id, status)
        elif job.job_type == "search.rebuild":
            _run_search_rebuild(store, job, worker_id)
        else:
            store.fail_job(job.id, error=f"unknown job type {job.job_type}")
            log.warning("unknown job type id=%s type=%s", job.id, job.job_type)

    # 3. Computer timeouts
    idle_seconds = int(os.environ.get("COMPUTER_TAKEOVER_IDLE_SECONDS", "120") or "120")
    try:
        store.expire_idle_takeovers(idle_seconds)
    except Exception:
        log.exception("idle takeover expire failed")
    for bot_id in store.due_idle_computer_bots():
        status = stop_computer(base, token, bot_id)
        if status in {200, 201}:
            log.info("computer slept bot=%s", bot_id)
        elif status not in {409}:
            log.warning("computer sleep failed bot=%s status=%s", bot_id, status)
    return woke


def _run_search_rebuild(store: HistoryStore, job: object, worker_id: str) -> None:
    payload = dict(getattr(job, "payload", None) or {})
    job_id = str(getattr(job, "id", "") or "")
    try:
        for _ in range(40):
            store.heartbeat_job(job_id, worker_id)
            payload, done = store.rebuild_search_chunk(payload)
            store.update_job_payload(job_id, payload, worker_id=worker_id)
            if done:
                store.ack_job(job_id, result={"rebuilt": True, "phase": payload.get("phase")})
                log.info("search rebuild finished id=%s", job_id)
                return
        log.info("search rebuild yielded id=%s phase=%s", job_id, payload.get("phase"))
    except Exception:
        log.exception("search rebuild failed id=%s", job_id)
        store.fail_job(job_id, error="search rebuild failed")


def worker(*, once: bool = False) -> int:
    configure_logging()
    url = os.environ.get(
        "DATABASE_URL",
        "postgresql://artek:artek@127.0.0.1:5432/artek_buddy",
    )
    token = os.environ.get("AGENT_HTTP_TOKEN", "").strip()
    if not token:
        log.error("AGENT_HTTP_TOKEN is required")
        return 1
    poll = int(os.environ.get("WORKER_POLL_SECONDS", DEFAULT_POLL_SECONDS) or DEFAULT_POLL_SECONDS)
    poll = max(5, min(poll, 300))
    store = HistoryStore(url)
    try:
        store.open()
        store.apply_migrations()
        store.ensure_search_index()
    except DatabaseUnavailable as err:
        log.error("worker db unavailable: %s", err)
        return 1
    base = host_base()
    try:
        if once:
            run_once(store, base, token)
            return 0
        log.info("worker polling every %ss", poll)
        while True:
            try:
                run_once(store, base, token)
            except DatabaseUnavailable:
                log.warning("worker db unavailable, backing off for %ss", poll)
            except Exception:
                log.exception("worker loop error")
            time.sleep(poll)
    except KeyboardInterrupt:
        return 0
    finally:
        store.close()
