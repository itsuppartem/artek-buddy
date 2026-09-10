from __future__ import annotations

from tests.api.helpers import create_bot, wait_run, wait_run_status, wait_thread_has

from artek_buddy.db.shaping import UNKNOWN_OUTCOME_TEXT


def _user_texts(payload: dict) -> list[str]:
    found: list[str] = []
    for msg in payload.get("messages") or []:
        if msg.get("role") != "user":
            continue
        for block in msg.get("blocks") or []:
            if block.get("kind") == "text" and block.get("text"):
                found.append(str(block["text"]))
    return found


def test_lost_http_after_accept_reuses_command_id(client, auth_header) -> None:
    bot_id = create_bot(client, auth_header, "CmdLost")["id"]
    body = {"text": "hello", "command_id": "cmd_lost_hello"}
    first = client.post(f"/v1/threads/{bot_id}/messages", headers=auth_header, json=body)
    assert first.status_code == 200, first.text
    second = client.post(f"/v1/threads/{bot_id}/messages", headers=auth_header, json=body)
    assert second.status_code == 200, second.text
    assert first.json()["run_id"] == second.json()["run_id"]
    done = wait_run(client, auth_header, bot_id, first.json()["run_id"])
    assert done["run"]["status"] == "completed"
    assert _user_texts(done).count("hello") == 1


def test_same_command_id_changed_payload_is_conflict(client, auth_header) -> None:
    bot_id = create_bot(client, auth_header, "CmdMismatch")["id"]
    first = client.post(
        f"/v1/threads/{bot_id}/messages",
        headers=auth_header,
        json={"text": "hello", "command_id": "cmd_mismatch"},
    )
    assert first.status_code == 200, first.text
    wait_run(client, auth_header, bot_id, first.json()["run_id"])
    changed = client.post(
        f"/v1/threads/{bot_id}/messages",
        headers=auth_header,
        json={"text": "other", "command_id": "cmd_mismatch"},
    )
    assert changed.status_code == 409
    assert "different message" in changed.json()["detail"]


def test_timeout_after_run_id_is_unknown_not_a_second_send(client, auth_header) -> None:
    bot_id = create_bot(client, auth_header, "CmdUnknown")["id"]
    command_id = "cmd_unknown_timeout"
    sent = client.post(
        f"/v1/threads/{bot_id}/messages",
        headers=auth_header,
        json={"text": "please e2e-unknown-timeout", "command_id": command_id},
    )
    assert sent.status_code == 200, sent.text
    run_id = sent.json()["run_id"]
    parked = wait_run_status(client, auth_header, bot_id, run_id, "unknown")
    assert parked["run"]["status"] == "unknown"
    assert parked["run"]["status"] != "failed"
    assert parked["run"].get("error") == UNKNOWN_OUTCOME_TEXT
    listed = client.get("/v1/bots", headers=auth_header).json()["bots"]
    row = next(item for item in listed if item["id"] == bot_id)
    assert row["execution_state"] == "unconfirmed"
    retry = client.post(
        f"/v1/threads/{bot_id}/messages",
        headers=auth_header,
        json={"text": "please e2e-unknown-timeout", "command_id": command_id},
    )
    assert retry.status_code == 200, retry.text
    assert retry.json()["run_id"] == run_id
    after = client.get(f"/v1/threads/{bot_id}", headers=auth_header).json()
    assert _user_texts(after).count("please e2e-unknown-timeout") == 1


def test_new_attempt_after_unknown_is_linked_and_does_not_revive_stop(client, auth_header) -> None:
    bot_id = create_bot(client, auth_header, "CmdAttempt")["id"]
    first = client.post(
        f"/v1/threads/{bot_id}/messages",
        headers=auth_header,
        json={"text": "please e2e-unknown-timeout", "command_id": "cmd_attempt_a"},
    )
    assert first.status_code == 200, first.text
    run_id = first.json()["run_id"]
    wait_run_status(client, auth_header, bot_id, run_id, "unknown")
    nxt = client.post(
        f"/v1/threads/{bot_id}/messages",
        headers=auth_header,
        json={
            "text": "hello",
            "command_id": "cmd_attempt_b",
            "parent_command_id": "cmd_attempt_a",
        },
    )
    assert nxt.status_code == 200, nxt.text
    assert nxt.json()["run_id"] != run_id
    parked = client.get(f"/v1/threads/{bot_id}", headers=auth_header).json()
    del parked
    store = client.app.state.store
    leftover = store.get_run(run_id)
    assert leftover is not None
    assert leftover.status == "cancelled"
    wait_run(client, auth_header, bot_id, nxt.json()["run_id"])
    store.finish_turn(
        store.get_bot(bot_id),
        leftover,
        "late complete from unknown",
        "completed",
    )
    still = store.get_run(run_id)
    assert still is not None
    assert still.status == "cancelled"
    wait_thread_has(client, auth_header, bot_id, "ok")
    found = store.get_owner_command(bot_id, "cmd_attempt_b")
    assert found is not None
    assert found.parent_command_id == "cmd_attempt_a"


def test_stop_during_unknown_rejects_late_complete(client, auth_header) -> None:
    bot_id = create_bot(client, auth_header, "CmdStop")["id"]
    sent = client.post(
        f"/v1/threads/{bot_id}/messages",
        headers=auth_header,
        json={"text": "please e2e-unknown-timeout", "command_id": "cmd_stop_unk"},
    )
    assert sent.status_code == 200, sent.text
    run_id = sent.json()["run_id"]
    wait_run_status(client, auth_header, bot_id, run_id, "unknown")
    stopped = client.post(f"/v1/threads/{bot_id}/stop", headers=auth_header)
    assert stopped.status_code == 200, stopped.text
    store = client.app.state.store
    leftover = store.get_run(run_id)
    assert leftover is not None
    assert leftover.status == "cancelled"
    store.finish_turn(
        store.get_bot(bot_id),
        leftover,
        "late complete from unknown",
        "completed",
    )
    still = store.get_run(run_id)
    assert still is not None
    assert still.status == "cancelled"
