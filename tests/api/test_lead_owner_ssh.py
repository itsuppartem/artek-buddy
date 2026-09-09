from __future__ import annotations

from tests.api.helpers import create_bot, message_texts, wait_run

from artek_buddy.runtime.scripted import E2E_LEAD_OWNER_SSH


def test_lead_owner_ssh_is_refused_and_turn_finishes(client, auth_header) -> None:
    bot_id = create_bot(client, auth_header, "LeadSshRefuse")["id"]
    sent = client.post(
        f"/v1/threads/{bot_id}/messages",
        headers=auth_header,
        json={"text": "please e2e-lead-owner-ssh"},
    )
    assert sent.status_code == 200
    run_id = sent.json()["run_id"]
    snap = wait_run(client, auth_header, bot_id, run_id)
    assert snap["run"]["status"] == "completed"
    assert E2E_LEAD_OWNER_SSH in message_texts(snap)
    later = client.post(
        f"/v1/threads/{bot_id}/messages",
        headers=auth_header,
        json={"text": "please e2e-slow now"},
    )
    assert later.status_code == 200
    assert later.json().get("queued") is not True
    assert later.json()["run_id"] != run_id


def test_stop_waiting_input_cannot_resurrect_cancelled_run(client, auth_header) -> None:
    from artek_buddy.main import app

    bot_id = create_bot(client, auth_header, "StopNoZombie")["id"]
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
    revived = app.state.store.mark_run_waiting_input(run_id)
    assert revived is None
    after = client.get(f"/v1/threads/{bot_id}", headers=auth_header)
    assert after.status_code == 200
    assert after.json()["run"]["status"] == "cancelled"
    nxt = client.post(
        f"/v1/threads/{bot_id}/messages",
        headers=auth_header,
        json={"text": "hello after stop"},
    )
    assert nxt.status_code == 200
    assert nxt.json().get("queued") is not True
    assert nxt.json()["run_id"] != run_id
