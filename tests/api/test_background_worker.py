from __future__ import annotations

import time

from tests.api.helpers import create_bot, message_texts, wait_run, wait_thread_has

WORKER_NAME = "Researcher"
WORKER_ACK = "Working in the background."
WORKER_STATUS = "Still working."
WORKER_STEER_ACK = "Got it. I'll apply that next."
WORKER_SUMMARY = "The background job is done."
WORKER_RESULT = "blocked work finished"


def _workers(client, auth_header: dict[str, str], bot_id: str) -> list[dict]:
    listed = client.get(f"/v1/bots/{bot_id}/subagents", headers=auth_header)
    assert listed.status_code == 200, listed.text
    return listed.json()["subagents"]


def _running(workers: list[dict]) -> list[dict]:
    return [item for item in workers if item.get("status") in {"queued", "running"}]


def wait_worker_step(
    client,
    auth_header: dict[str, str],
    bot_id: str,
    step: str,
    remaining: str | None = None,
    timeout: float = 5.0,
) -> dict:
    deadline = time.time() + timeout
    last: list[dict] = []
    while time.time() < deadline:
        last = _workers(client, auth_header, bot_id)
        for item in last:
            if item.get("progress") != step:
                continue
            if remaining is not None and item.get("progress_remaining") != remaining:
                continue
            snap = client.get(f"/v1/threads/{bot_id}", headers=auth_header)
            assert snap.status_code == 200
            return snap.json()
        time.sleep(0.1)
    raise AssertionError(f"{bot_id} never reached progress {step!r}: {last}")


def test_simple_chat_does_not_spawn_a_worker(client, auth_header) -> None:
    bot_id = create_bot(client, auth_header, "DirectLead")["id"]
    sent = client.post(
        f"/v1/threads/{bot_id}/messages",
        headers=auth_header,
        json={"text": "hello"},
    )
    assert sent.status_code == 200
    snap = wait_run(client, auth_header, bot_id, sent.json()["run_id"])
    assert snap["run"]["status"] == "completed"
    assert _workers(client, auth_header, bot_id) == []


def test_background_worker_chat_keeps_lead_free(client, auth_header) -> None:
    bot_id = create_bot(client, auth_header, "BgLead")["id"]
    sent = client.post(
        f"/v1/threads/{bot_id}/messages",
        headers=auth_header,
        json={"text": "please e2e-background-worker-chat"},
    )
    assert sent.status_code == 200
    lead_id = sent.json()["run_id"]
    started = time.monotonic()
    snap = wait_run(client, auth_header, bot_id, lead_id)
    assert snap["run"]["status"] == "completed"
    assert time.monotonic() - started < 2
    assert WORKER_ACK in message_texts(snap)
    workers = _running(_workers(client, auth_header, bot_id))
    assert len(workers) == 1
    worker_id = workers[0]["id"]
    assert workers[0]["status"] == "running"
    assert workers[0]["name"] == WORKER_NAME
    assert not any(text.startswith("Started ") for text in message_texts(snap))
    reconnect = client.get(f"/v1/threads/{bot_id}", headers=auth_header)
    assert reconnect.status_code == 200
    body = reconnect.json()
    assert body["run"]["id"] == lead_id
    assert body["run"]["status"] == "completed"
    assert any(
        item["id"] == worker_id and item["status"] == "running"
        for item in (body.get("subagents") or [])
    )

    status_started = time.monotonic()
    status = client.post(
        f"/v1/threads/{bot_id}/messages",
        headers=auth_header,
        json={"text": "please e2e-worker-status"},
    )
    assert status.status_code == 200
    status_id = status.json()["run_id"]
    assert status_id != lead_id
    status_snap = wait_run(client, auth_header, bot_id, status_id)
    assert time.monotonic() - status_started < 2
    assert status_snap["run"]["status"] == "completed"
    assert WORKER_STATUS in message_texts(status_snap)
    after_status = _workers(client, auth_header, bot_id)
    assert after_status[0]["id"] == worker_id
    assert after_status[0]["status"] == "running"

    done = wait_thread_has(client, auth_header, bot_id, WORKER_SUMMARY, timeout=20)
    texts = message_texts(done)
    assert texts.count(WORKER_SUMMARY) == 1
    assert WORKER_RESULT not in texts
    assert not any(text.startswith(("Started ", "Finished ", "Stopped ")) for text in texts)
    finished = [item for item in _workers(client, auth_header, bot_id) if item["id"] == worker_id]
    assert finished and finished[0]["status"] == "completed"


def test_worker_steer_applies_once_without_restart(client, auth_header) -> None:
    bot_id = create_bot(client, auth_header, "SteerLead")["id"]
    sent = client.post(
        f"/v1/threads/{bot_id}/messages",
        headers=auth_header,
        json={"text": "please e2e-background-worker-chat"},
    )
    assert sent.status_code == 200
    wait_run(client, auth_header, bot_id, sent.json()["run_id"])
    worker = _running(_workers(client, auth_header, bot_id))[0]
    worker_id = worker["id"]

    steer = client.post(
        f"/v1/threads/{bot_id}/messages",
        headers=auth_header,
        json={"text": "please e2e-worker-steer use path B"},
    )
    assert steer.status_code == 200
    steer_snap = wait_run(client, auth_header, bot_id, steer.json()["run_id"])
    assert WORKER_STEER_ACK in message_texts(steer_snap)
    mid = _workers(client, auth_header, bot_id)[0]
    assert mid["id"] == worker_id
    assert mid["status"] == "running"
    assert "path B" in (mid.get("clarifications") or "")

    done = wait_thread_has(client, auth_header, bot_id, WORKER_SUMMARY, timeout=20)
    assert WORKER_SUMMARY in message_texts(done)
    final = [item for item in _workers(client, auth_header, bot_id) if item["id"] == worker_id]
    assert final and final[0]["status"] == "completed"
    assert final[0].get("result") == "path B done"


def test_stop_cancels_worker_when_lead_is_idle(client, auth_header) -> None:
    bot_id = create_bot(client, auth_header, "StopLead")["id"]
    sent = client.post(
        f"/v1/threads/{bot_id}/messages",
        headers=auth_header,
        json={"text": "please e2e-background-worker-chat"},
    )
    assert sent.status_code == 200
    wait_run(client, auth_header, bot_id, sent.json()["run_id"])
    assert _running(_workers(client, auth_header, bot_id))
    stopped = client.post(f"/v1/threads/{bot_id}/stop", headers=auth_header)
    assert stopped.status_code == 200
    deadline = time.time() + 5
    last: list[dict] = []
    while time.time() < deadline:
        last = _workers(client, auth_header, bot_id)
        if last and last[0]["status"] == "cancelled":
            snap = client.get(f"/v1/threads/{bot_id}", headers=auth_header)
            assert snap.status_code == 200
            assert snap.json()["run"]["status"] == "cancelled"
            assert snap.json()["run"]["error"] == "Stopped."
            return
        time.sleep(0.1)
    raise AssertionError(f"worker was not cancelled: {last}")


def test_worker_progress_stays_off_the_transcript(client, auth_header) -> None:
    from artek_buddy.runtime.scripted import (
        E2E_WORKER_ACK,
        E2E_WORKER_PROGRESS_LINE,
        E2E_WORKER_PROGRESS_LINE_2,
        E2E_WORKER_PROGRESS_RESULT,
        E2E_WORKER_SUMMARY,
    )

    bot_id = create_bot(client, auth_header, "WorkerProgressLead")["id"]
    sent = client.post(
        f"/v1/threads/{bot_id}/messages",
        headers=auth_header,
        json={"text": "please e2e-worker-progress"},
    )
    assert sent.status_code == 200
    lead = wait_run(client, auth_header, bot_id, sent.json()["run_id"])
    assert lead["run"]["status"] == "completed"
    assert E2E_WORKER_ACK in message_texts(lead)

    first = wait_worker_step(client, auth_header, bot_id, "commit", "push MR 76")
    assert E2E_WORKER_PROGRESS_LINE not in message_texts(first)
    workers = _running(_workers(client, auth_header, bot_id))
    assert len(workers) == 1
    reconnect = client.get(f"/v1/threads/{bot_id}", headers=auth_header)
    assert reconnect.status_code == 200
    body = reconnect.json()
    assert any(
        item.get("progress") == "commit" and item.get("progress_remaining") == "push MR 76"
        for item in (body.get("subagents") or [])
    )

    second = wait_worker_step(client, auth_header, bot_id, "push MR 76", "comment on the ticket")
    texts = message_texts(second)
    assert E2E_WORKER_PROGRESS_LINE not in texts
    assert E2E_WORKER_PROGRESS_LINE_2 not in texts

    done = wait_thread_has(client, auth_header, bot_id, E2E_WORKER_SUMMARY, timeout=20)
    final_texts = message_texts(done)
    assert final_texts.count(E2E_WORKER_SUMMARY) == 1
    assert E2E_WORKER_PROGRESS_LINE not in final_texts
    assert E2E_WORKER_PROGRESS_LINE_2 not in final_texts
    assert E2E_WORKER_PROGRESS_RESULT not in final_texts
    finished = [
        item for item in _workers(client, auth_header, bot_id) if item["status"] == "completed"
    ]
    assert finished and "progress job done" in (finished[0].get("result") or "")


def test_stop_ends_worker_progress_heartbeats(client, auth_header) -> None:
    from artek_buddy.runtime.scripted import E2E_WORKER_PROGRESS_LINE, E2E_WORKER_PROGRESS_LINE_2

    bot_id = create_bot(client, auth_header, "StopProgress")["id"]
    sent = client.post(
        f"/v1/threads/{bot_id}/messages",
        headers=auth_header,
        json={"text": "please e2e-worker-progress"},
    )
    assert sent.status_code == 200
    wait_run(client, auth_header, bot_id, sent.json()["run_id"])
    wait_worker_step(client, auth_header, bot_id, "commit", "push MR 76")
    stopped = client.post(f"/v1/threads/{bot_id}/stop", headers=auth_header)
    assert stopped.status_code == 200
    deadline = time.time() + 5
    last: list[dict] = []
    while time.time() < deadline:
        last = _workers(client, auth_header, bot_id)
        if last and last[0]["status"] == "cancelled":
            snap = client.get(f"/v1/threads/{bot_id}", headers=auth_header)
            assert snap.status_code == 200
            texts = message_texts(snap.json())
            assert E2E_WORKER_PROGRESS_LINE not in texts
            assert E2E_WORKER_PROGRESS_LINE_2 not in texts
            assert snap.json()["run"]["error"] == "Stopped."
            return
        time.sleep(0.1)
    raise AssertionError(f"progress worker was not cancelled: {last}")
