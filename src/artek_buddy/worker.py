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


def wake_routine(base: str, token: str, bot_id: str, prompt: str, timeout: float = 30) -> int:
    request_id = mint_request_id()
    request = urllib.request.Request(
        f"{base.rstrip('/')}/v1/threads/{bot_id}/messages",
        data=json.dumps({"text": prompt, "trigger": "routine"}).encode("utf-8"),
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
        store.enqueue_job(
            job_type="routine.fire",
            resource_id=routine.id,
            idempotency_key=idempotency_key,
            payload={
                "version": 1,
                "routine_id": routine.id,
                "bot_id": routine.bot_id,
                "prompt": routine.prompt,
            },
            max_attempts=5,
        )
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
            status = wake_routine(base, token, bot_id, prompt)
            if status in {200, 201}:
                store.ack_job(job.id, result={"status": status})
                woke += 1
                log.info("routine job succeeded id=%s status=%s", job.id, status)
            elif status == 409:
                store.ack_job(job.id, result={"status": status, "skipped": "busy"})
                log.info("routine job skipped busy id=%s", job.id)
            else:
                store.fail_job(job.id, error=f"HTTP {status}")
                log.warning("routine job failed id=%s status=%s", job.id, status)

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
