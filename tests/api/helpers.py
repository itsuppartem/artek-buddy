from __future__ import annotations

import time
from typing import Any


def create_bot(client, auth_header: dict[str, str], name: str, **extra: Any) -> dict[str, Any]:
    response = client.post("/v1/bots", headers=auth_header, json={"name": name, **extra})
    assert response.status_code == 200, response.text
    return response.json()


def wait_run(
    client, auth_header: dict[str, str], bot_id: str, run_id: str, timeout: float = 15.0
) -> dict[str, Any]:
    deadline = time.time() + timeout
    last: dict[str, Any] = {}
    store = client.app.state.store
    while time.time() < deadline:
        snap = client.get(f"/v1/threads/{bot_id}", headers=auth_header)
        assert snap.status_code == 200, snap.text
        last = snap.json()
        record = store.get_run(run_id)
        if record is not None and record.status in {"completed", "failed", "cancelled"}:
            snap = client.get(f"/v1/threads/{bot_id}", headers=auth_header)
            assert snap.status_code == 200, snap.text
            last = snap.json()
            return {**last, "run": record.model_dump(mode="json")}
        time.sleep(0.1)
    stored = store.get_run(run_id)
    raise AssertionError(f"turn {run_id} did not finish: {last.get('run')} stored={stored}")


def wait_pending_auto_jobs(
    client,
    auth_header: dict[str, str],
    bot_id: str,
    timeout: float = 15.0,
) -> dict[str, Any]:
    deadline = time.time() + timeout
    last: dict[str, Any] = {}
    while time.time() < deadline:
        snap = client.get(f"/v1/threads/{bot_id}", headers=auth_header)
        assert snap.status_code == 200, snap.text
        last = snap.json()
        pending = last.get("pending_auto_consent_ids") or []
        if pending:
            return last
        time.sleep(0.1)
    raise AssertionError(f"{bot_id} never listed a queued automatic owner job: {last}")


def wait_run_status(
    client,
    auth_header: dict[str, str],
    bot_id: str,
    run_id: str,
    status: str,
    timeout: float = 15.0,
) -> dict[str, Any]:
    deadline = time.time() + timeout
    last: dict[str, Any] = {}
    store = client.app.state.store
    while time.time() < deadline:
        snap = client.get(f"/v1/threads/{bot_id}", headers=auth_header)
        assert snap.status_code == 200, snap.text
        last = snap.json()
        run = last.get("run") or {}
        if run.get("id") == run_id and run.get("status") == status:
            return last
        record = store.get_run(run_id)
        if (
            record is not None
            and record.status == status
            and status in {"completed", "failed", "cancelled"}
        ):
            return {**last, "run": record.model_dump(mode="json")}
        time.sleep(0.1)
    stored = store.get_run(run_id)
    raise AssertionError(f"turn {run_id} not {status}: {last.get('run')} stored={stored}")


def wait_thread_has(
    client,
    auth_header: dict[str, str],
    bot_id: str,
    needle: str,
    timeout: float = 15.0,
) -> dict[str, Any]:
    deadline = time.time() + timeout
    last: dict[str, Any] = {}
    while time.time() < deadline:
        snap = client.get(f"/v1/threads/{bot_id}", headers=auth_header)
        assert snap.status_code == 200, snap.text
        last = snap.json()
        blob = "\n".join(message_texts(last))
        if needle in blob:
            return last
        time.sleep(0.1)
    raise AssertionError(f"{bot_id} never showed {needle!r}: {message_texts(last)}")


def message_texts(payload: dict[str, Any]) -> list[str]:
    texts: list[str] = []
    for msg in payload.get("messages") or []:
        for block in msg.get("blocks") or []:
            text = block.get("text")
            if block.get("kind") == "text" and text:
                texts.append(str(text))
    return texts


def message_metas(payload: dict[str, Any]) -> list[str]:
    texts: list[str] = []
    for msg in payload.get("messages") or []:
        for block in msg.get("blocks") or []:
            text = block.get("text")
            if block.get("kind") == "meta" and text:
                texts.append(str(text))
    return texts


def consent_id_from_thread(snap: dict[str, Any]) -> str:
    for msg in snap.get("messages") or []:
        for block in msg.get("blocks") or []:
            cid = block.get("consent_id")
            if cid:
                return str(cid)
    raise AssertionError("no consent_id on the thread")
