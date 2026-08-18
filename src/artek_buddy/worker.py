from __future__ import annotations

import json
import logging
import os
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone

from artek_buddy.db import DatabaseUnavailable
from artek_buddy.db.history import HistoryStore
from artek_buddy.db.shaping import isoformat_utc

log = logging.getLogger("artek_buddy.worker")

DEFAULT_POLL_SECONDS = 15
RETRY_SECONDS = 60


def host_base() -> str:
    port = os.environ.get("HTTP_PORT", "8080").strip() or "8080"
    return f"http://127.0.0.1:{port}"


def wake_routine(base: str, token: str, bot_id: str, prompt: str, timeout: float = 30) -> int:
    request = urllib.request.Request(
        f"{base.rstrip('/')}/v1/threads/{bot_id}/messages",
        data=json.dumps({"text": prompt, "trigger": "routine"}).encode("utf-8"),
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
    due = store.claim_due_routines()
    woke = 0
    for routine in due:
        status = wake_routine(base, token, routine.bot_id, routine.prompt)
        if status in {200, 201}:
            woke += 1
            log.info("routine woke id=%s status=%s", routine.id, status)
        elif status == 409:
            log.info("routine skipped busy id=%s", routine.id)
        else:
            retry = datetime.now(timezone.utc) + timedelta(seconds=RETRY_SECONDS)
            store.reschedule_routine(routine.id, isoformat_utc(retry))
            log.warning("routine wake failed id=%s status=%s", routine.id, status)
    for bot_id in store.due_idle_computer_bots():
        status = stop_computer(base, token, bot_id)
        if status in {200, 201}:
            log.info("computer slept bot=%s", bot_id)
        elif status not in {409}:
            log.warning("computer sleep failed bot=%s status=%s", bot_id, status)
    return woke


def worker() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
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
    log.info("worker polling every %ss", poll)
    try:
        while True:
            try:
                run_once(store, base, token)
            except DatabaseUnavailable:
                log.exception("worker db")
            time.sleep(poll)
    except KeyboardInterrupt:
        return 0
    finally:
        store.close()
