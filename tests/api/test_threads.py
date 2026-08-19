from __future__ import annotations

import time


def _create_bot(client, auth_header, name: str = "Chat") -> str:
    response = client.post("/v1/bots", headers=auth_header, json={"name": name})
    assert response.status_code == 200
    return response.json()["id"]


def _wait_run(client, auth_header, bot_id: str, timeout: float = 15.0) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        snap = client.get(f"/v1/threads/{bot_id}", headers=auth_header)
        assert snap.status_code == 200
        run = snap.json().get("run")
        status = (run or {}).get("status")
        if status in {"completed", "failed", "cancelled"}:
            return snap.json()
        time.sleep(0.15)
    raise AssertionError("turn did not finish")


def test_scripted_turn_happy_and_fail(client, auth_header) -> None:
    bot_id = _create_bot(client, auth_header, "Scripted")
    sent = client.post(
        f"/v1/threads/{bot_id}/messages",
        headers=auth_header,
        json={"text": "hello"},
    )
    assert sent.status_code == 200
    snap = _wait_run(client, auth_header, bot_id)
    assert snap["run"]["status"] == "completed"
    roles = [msg["role"] for msg in snap["messages"]]
    assert "user" in roles
    assert "bot" in roles

    first_run = snap["run"]["id"]
    fail = client.post(
        f"/v1/threads/{bot_id}/messages",
        headers=auth_header,
        json={"text": "please e2e-fail now"},
    )
    assert fail.status_code == 200
    deadline = time.time() + 15
    failed = None
    while time.time() < deadline:
        current = client.get(f"/v1/threads/{bot_id}", headers=auth_header).json()
        run = current.get("run") or {}
        if run.get("id") != first_run and run.get("status") in {"completed", "failed", "cancelled"}:
            failed = current
            break
        time.sleep(0.15)
    assert failed is not None, "fail turn did not start"
    assert failed["run"]["status"] == "failed"


def test_send_without_auth(client) -> None:
    response = client.post("/v1/threads/bot_missing/messages", json={"text": "hi"})
    assert response.status_code in {401, 404}
