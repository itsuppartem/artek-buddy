from __future__ import annotations

import time

from tests.api.helpers import create_bot, message_texts, wait_run, wait_run_status

from artek_buddy.runtime.scripted_scenarios import (
    E2E_SPECIFIED_ANSWER,
    E2E_UNCLEAR_ANSWER,
    E2E_UNCLEAR_QUESTION,
    E2E_WORKER_UNCLEAR_ANSWER,
    E2E_WORKER_UNCLEAR_QUESTION,
)


def _pending_asks(payload: dict) -> list[tuple[dict, dict]]:
    found: list[tuple[dict, dict]] = []
    for message in payload.get("messages") or []:
        for block in message.get("blocks") or []:
            if (
                block.get("kind") == "ask"
                and block.get("status") == "pending"
                and not block.get("consent_id")
            ):
                found.append((message, block))
    return found


def _workers(client, auth_header: dict[str, str], bot_id: str) -> list[dict]:
    listed = client.get(f"/v1/bots/{bot_id}/subagents", headers=auth_header)
    assert listed.status_code == 200, listed.text
    return listed.json()["subagents"]


def test_unclear_assignment_parks_on_ask_user(client, auth_header) -> None:
    bot_id = create_bot(client, auth_header, "UnclearLeadAsk")["id"]
    sent = client.post(
        f"/v1/threads/{bot_id}/messages",
        headers=auth_header,
        json={"text": "please e2e-unclear-assignment"},
    )
    assert sent.status_code == 200
    run_id = sent.json()["run_id"]
    waiting = wait_run_status(client, auth_header, bot_id, run_id, "waiting_input", timeout=5)
    pending = _pending_asks(waiting)
    assert len(pending) == 1
    message, block = pending[0]
    assert E2E_UNCLEAR_QUESTION in (block.get("text") or "")

    answered = client.post(
        f"/v1/threads/{bot_id}/answer",
        headers=auth_header,
        json={
            "run_id": run_id,
            "message_id": message["id"],
            "answer": "Use notes.md in the Research chat",
        },
    )
    assert answered.status_code == 200, answered.text
    finished = wait_run(client, auth_header, bot_id, run_id)
    assert finished["run"]["id"] == run_id
    assert finished["run"]["status"] == "completed"
    answered_message = next(item for item in finished["messages"] if item["id"] == message["id"])
    answered_block = next(
        block for block in answered_message["blocks"] if block.get("kind") == "ask"
    )
    assert answered_block["status"] == "answered"
    assert answered_block["answer"] == "Use notes.md in the Research chat"
    assert any(
        block.get("kind") == "text" and E2E_UNCLEAR_ANSWER in block.get("text", "")
        for item in finished["messages"]
        for block in item["blocks"]
    )


def test_specified_assignment_does_not_park_on_ask_user(client, auth_header) -> None:
    bot_id = create_bot(client, auth_header, "SpecifiedNoAsk")["id"]
    sent = client.post(
        f"/v1/threads/{bot_id}/messages",
        headers=auth_header,
        json={"text": "please e2e-specified-assignment"},
    )
    assert sent.status_code == 200
    finished = wait_run(client, auth_header, bot_id, sent.json()["run_id"])
    assert finished["run"]["status"] == "completed"
    asks = [
        block
        for item in finished["messages"]
        for block in item["blocks"]
        if block.get("kind") == "ask"
    ]
    assert asks == []
    assert any(
        block.get("kind") == "text" and E2E_SPECIFIED_ANSWER in block.get("text", "")
        for item in finished["messages"]
        for block in item["blocks"]
    )


def test_worker_unclear_assignment_parks_on_ask_user(client, auth_header) -> None:
    bot_id = create_bot(client, auth_header, "WorkerUnclearAsk")["id"]
    sent = client.post(
        f"/v1/threads/{bot_id}/messages",
        headers=auth_header,
        json={"text": "please e2e-worker-unclear-assignment"},
    )
    assert sent.status_code == 200
    wait_run(client, auth_header, bot_id, sent.json()["run_id"])
    deadline = time.time() + 8
    last: dict = {}
    pending: list[tuple[dict, dict]] = []
    while time.time() < deadline:
        snap = client.get(f"/v1/threads/{bot_id}", headers=auth_header)
        assert snap.status_code == 200
        last = snap.json()
        pending = _pending_asks(last)
        if pending:
            break
        time.sleep(0.1)
    else:
        raise AssertionError(f"worker unclear ask never appeared: {message_texts(last)}")
    message, block = pending[0]
    assert E2E_WORKER_UNCLEAR_QUESTION in (block.get("text") or "")
    run_id = message["run_id"]
    assert run_id != sent.json()["run_id"]
    workers = [item for item in _workers(client, auth_header, bot_id) if item["id"] == run_id]
    assert workers and workers[0]["id"] == run_id
    answered = client.post(
        f"/v1/threads/{bot_id}/answer",
        headers=auth_header,
        json={
            "run_id": run_id,
            "message_id": message["id"],
            "answer": "Build notes.md for Research",
        },
    )
    assert answered.status_code == 200, answered.text
    deadline = time.time() + 15
    finished: list[dict] = []
    while time.time() < deadline:
        finished = [item for item in _workers(client, auth_header, bot_id) if item["id"] == run_id]
        if finished and finished[0]["status"] == "completed":
            break
        time.sleep(0.1)
    else:
        raise AssertionError(f"worker did not resume after unclear ask: {finished}")
    assert finished[0].get("result") == E2E_WORKER_UNCLEAR_ANSWER
