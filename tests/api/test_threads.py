from __future__ import annotations

import time


def _create_bot(client, auth_header, name: str = "Chat") -> str:
    response = client.post("/v1/bots", headers=auth_header, json={"name": name})
    assert response.status_code == 200
    return response.json()["id"]


def _wait_run(client, auth_header, bot_id: str, run_id: str, timeout: float = 15.0) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        snap = client.get(f"/v1/threads/{bot_id}", headers=auth_header)
        assert snap.status_code == 200
        body = snap.json()
        run = body.get("run") or {}
        if run.get("id") == run_id and run.get("status") in {"completed", "failed", "cancelled"}:
            return body
        time.sleep(0.15)
    raise AssertionError(f"turn {run_id} did not finish")


def test_scripted_turn_happy(client, auth_header) -> None:
    bot_id = _create_bot(client, auth_header, "Scripted")
    sent = client.post(
        f"/v1/threads/{bot_id}/messages",
        headers=auth_header,
        json={"text": "hello"},
    )
    assert sent.status_code == 200
    payload = sent.json()
    assert payload.get("queued") is not True
    snap = _wait_run(client, auth_header, bot_id, payload["run_id"])
    assert snap["run"]["status"] == "completed"
    roles = [msg["role"] for msg in snap["messages"]]
    assert "user" in roles
    assert "bot" in roles


def test_scripted_turn_fail(client, auth_header) -> None:
    bot_id = _create_bot(client, auth_header, "ScriptedFail")
    sent = client.post(
        f"/v1/threads/{bot_id}/messages",
        headers=auth_header,
        json={"text": "please e2e-fail now"},
    )
    assert sent.status_code == 200
    payload = sent.json()
    assert payload.get("queued") is not True
    snap = _wait_run(client, auth_header, bot_id, payload["run_id"])
    assert snap["run"]["status"] == "failed"
    assert snap["run"].get("error")


def test_send_without_auth(client) -> None:
    response = client.post("/v1/threads/bot_missing/messages", json={"text": "hi"})
    assert response.status_code in {401, 404}
