from __future__ import annotations

import time

from tests.api.helpers import create_bot, wait_run, wait_run_status


def test_scripted_turn_happy(client, auth_header) -> None:
    bot_id = create_bot(client, auth_header, "Scripted")["id"]
    sent = client.post(
        f"/v1/threads/{bot_id}/messages",
        headers=auth_header,
        json={"text": "hello"},
    )
    assert sent.status_code == 200
    payload = sent.json()
    assert payload.get("queued") is not True
    snap = wait_run(client, auth_header, bot_id, payload["run_id"])
    assert snap["run"]["status"] == "completed"
    roles = [msg["role"] for msg in snap["messages"]]
    assert "user" in roles
    assert "bot" in roles


def test_scripted_turn_fail(client, auth_header) -> None:
    bot_id = create_bot(client, auth_header, "ScriptedFail")["id"]
    sent = client.post(
        f"/v1/threads/{bot_id}/messages",
        headers=auth_header,
        json={"text": "please e2e-fail now"},
    )
    assert sent.status_code == 200
    payload = sent.json()
    assert payload.get("queued") is not True
    snap = wait_run(client, auth_header, bot_id, payload["run_id"])
    assert snap["run"]["status"] == "failed"
    assert snap["run"].get("error")


def test_send_without_auth_is_401(client) -> None:
    response = client.post("/v1/threads/bot_missing/messages", json={"text": "hi"})
    assert response.status_code == 401


def test_send_missing_bot_is_404(client, auth_header) -> None:
    response = client.post(
        "/v1/threads/bot_missing/messages",
        headers=auth_header,
        json={"text": "hi"},
    )
    assert response.status_code == 404


def test_send_empty_text_is_422(client, auth_header) -> None:
    bot_id = create_bot(client, auth_header, "EmptySend")["id"]
    response = client.post(
        f"/v1/threads/{bot_id}/messages",
        headers=auth_header,
        json={"text": "   "},
    )
    assert response.status_code == 422


def test_stop_missing_bot_is_404(client, auth_header) -> None:
    response = client.post("/v1/threads/bot_missing/stop", headers=auth_header)
    assert response.status_code == 404


def test_stop_cancels_slow_turn(client, auth_header) -> None:
    bot_id = create_bot(client, auth_header, "StopSlow")["id"]
    sent = client.post(
        f"/v1/threads/{bot_id}/messages",
        headers=auth_header,
        json={"text": "please e2e-slow now"},
    )
    assert sent.status_code == 200
    run_id = sent.json()["run_id"]
    stopped = client.post(f"/v1/threads/{bot_id}/stop", headers=auth_header)
    assert stopped.status_code == 200
    snap = wait_run(client, auth_header, bot_id, run_id)
    assert snap["run"]["status"] == "cancelled"


def test_follow_up_starts_a_new_turn(client, auth_header) -> None:
    bot_id = create_bot(client, auth_header, "Follow")["id"]
    sent = client.post(
        f"/v1/threads/{bot_id}/messages",
        headers=auth_header,
        json={"text": "hello"},
    )
    first = wait_run(client, auth_header, bot_id, sent.json()["run_id"])
    assert first["run"]["status"] == "completed"
    follow = client.post(
        f"/v1/threads/{bot_id}/follow-up",
        headers=auth_header,
        json={"text": "hello"},
    )
    assert follow.status_code == 200
    deadline = time.time() + 5
    run_id = first["run"]["id"]
    while time.time() < deadline:
        later = client.get(f"/v1/threads/{bot_id}", headers=auth_header)
        assert later.status_code == 200
        rid = (later.json().get("run") or {}).get("id")
        if rid and rid != first["run"]["id"]:
            run_id = rid
            break
        time.sleep(0.1)
    else:
        raise AssertionError("follow-up did not start a new run")
    snap = wait_run(client, auth_header, bot_id, run_id)
    assert snap["run"]["status"] == "completed"


def test_mark_unread_then_read(client, auth_header) -> None:
    bot_id = create_bot(client, auth_header, "Unread")["id"]
    flagged = client.post(f"/v1/threads/{bot_id}/unread", headers=auth_header)
    assert flagged.status_code == 200
    bot = client.get(f"/v1/bots/{bot_id}", headers=auth_header)
    assert bot.status_code == 200
    assert bot.json()["unread"] is True
    cleared = client.post(f"/v1/threads/{bot_id}/read", headers=auth_header)
    assert cleared.status_code == 200
    again = client.get(f"/v1/bots/{bot_id}", headers=auth_header)
    assert again.json()["unread"] is False


def test_runs_create_completes_hello(client, auth_header) -> None:
    bot_id = create_bot(client, auth_header, "Runs")["id"]
    created = client.post("/v1/runs", headers=auth_header, json={"text": "hello", "bot_id": bot_id})
    assert created.status_code == 200
    run_id = created.json()["id"]
    snap = wait_run(client, auth_header, bot_id, run_id)
    assert snap["run"]["status"] == "completed"


def test_auto_owner_read_exposes_pending_consent(client, auth_header) -> None:
    """The paired client must see the auto job on the thread, not only on a live SSE frame."""
    bot_id = create_bot(client, auth_header, "AutoRead")["id"]
    sent = client.post(
        f"/v1/threads/{bot_id}/messages",
        headers=auth_header,
        json={"text": "e2e-consent-auto-read"},
    )
    assert sent.status_code == 200
    run_id = sent.json()["run_id"]
    snap = wait_run_status(client, auth_header, bot_id, run_id, "waiting_input", timeout=5)
    pending = snap.get("pending_auto_consent_id")
    assert pending
    job = client.get(f"/v1/consents/{pending}", headers=auth_header)
    assert job.status_code == 200
    body = job.json()
    assert body["action_class"] == "owner_read"
    assert body["path"] == "notes.txt"
    uploaded = client.post(
        f"/v1/consents/{pending}/file",
        headers=auth_header,
        json={"name": "notes.txt", "text": "notes from owner"},
    )
    assert uploaded.status_code == 200
    finished = wait_run(client, auth_header, bot_id, run_id)
    assert finished["run"]["status"] == "completed"
