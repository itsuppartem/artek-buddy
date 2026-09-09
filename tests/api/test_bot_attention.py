from __future__ import annotations

from tests.api.helpers import consent_id_from_thread, create_bot, wait_run, wait_run_status

from artek_buddy.bot_attention import merge_bot_projection
from artek_buddy.runtime.scripted_scenarios import E2E_NO_QUESTIONS_ANSWER


def _bot_row(client, auth_header: dict[str, str], bot_id: str) -> dict:
    listed = client.get("/v1/bots", headers=auth_header)
    assert listed.status_code == 200, listed.text
    for row in listed.json()["bots"]:
        if row["id"] == bot_id:
            return row
    raise AssertionError(f"{bot_id} missing from /v1/bots")


def test_unread_preview_with_question_is_not_a_decision(client, auth_header) -> None:
    bot_id = create_bot(client, auth_header, "PreviewTrap")["id"]
    sent = client.post(
        f"/v1/threads/{bot_id}/messages",
        headers=auth_header,
        json={"text": "please e2e-no-questions"},
    )
    assert sent.status_code == 200
    finished = wait_run(client, auth_header, bot_id, sent.json()["run_id"])
    assert finished["run"]["status"] == "completed"
    unread = client.post(f"/v1/threads/{bot_id}/unread", headers=auth_header)
    assert unread.status_code == 200, unread.text
    row = _bot_row(client, auth_header, bot_id)
    assert row["preview"] == E2E_NO_QUESTIONS_ANSWER
    assert "question" in row["preview"].lower()
    assert row["unread"] is True
    assert row["attention_reason"] == "none"
    assert row["execution_state"] == "completed"
    assert row["connection_state"] == "live"
    assert row["pending_consent_id"] is None
    assert row["pending_ask_id"] is None


def test_waiting_consent_maps_to_approval_without_preview(client, auth_header) -> None:
    bot_id = create_bot(client, auth_header, "ConsentToday")["id"]
    sent = client.post(
        f"/v1/threads/{bot_id}/messages",
        headers=auth_header,
        json={"text": "e2e-consent-browse"},
    )
    assert sent.status_code == 200
    run_id = sent.json()["run_id"]
    snap = wait_run_status(client, auth_header, bot_id, run_id, "waiting_input")
    consent_id = consent_id_from_thread(snap)
    row = _bot_row(client, auth_header, bot_id)
    assert row["execution_state"] == "waiting"
    assert row["attention_reason"] == "approval"
    assert row["pending_consent_id"] == consent_id
    allowed = client.post(
        f"/v1/consents/{consent_id}",
        headers=auth_header,
        json={"decision": "allow"},
    )
    assert allowed.status_code == 200, allowed.text
    wait_run(client, auth_header, bot_id, run_id)
    after = _bot_row(client, auth_header, bot_id)
    assert after["attention_reason"] == "none"
    assert after["pending_consent_id"] is None
    assert after["state_version"] >= row["state_version"]


def test_waiting_ask_maps_to_clarification(client, auth_header) -> None:
    bot_id = create_bot(client, auth_header, "AskToday")["id"]
    sent = client.post(
        f"/v1/threads/{bot_id}/messages",
        headers=auth_header,
        json={"text": "please e2e-ask"},
    )
    assert sent.status_code == 200
    run_id = sent.json()["run_id"]
    snap = wait_run_status(client, auth_header, bot_id, run_id, "waiting_input")
    row = _bot_row(client, auth_header, bot_id)
    assert row["execution_state"] == "waiting"
    assert row["attention_reason"] == "clarification"
    assert row["pending_ask_id"]
    pending = [
        (message, block)
        for message in snap["messages"]
        for block in message["blocks"]
        if block.get("kind") == "ask"
        and block.get("status") == "pending"
        and not block.get("consent_id")
    ]
    assert len(pending) == 1
    message, _block = pending[0]
    assert row["pending_ask_id"] == message["id"]
    answered = client.post(
        f"/v1/threads/{bot_id}/answer",
        headers=auth_header,
        json={"run_id": run_id, "message_id": message["id"], "answer": "Belgrade"},
    )
    assert answered.status_code == 200, answered.text
    wait_run(client, auth_header, bot_id, run_id)


def test_takeover_maps_to_attention_takeover(client, auth_header) -> None:
    bot_id = create_bot(client, auth_header, "TakeoverToday")["id"]
    sent = client.post(
        f"/v1/threads/{bot_id}/messages",
        headers=auth_header,
        json={"text": "please e2e-park-takeover"},
    )
    assert sent.status_code == 200
    run_id = sent.json()["run_id"]
    wait_run_status(client, auth_header, bot_id, run_id, "waiting_takeover")
    row = _bot_row(client, auth_header, bot_id)
    assert row["execution_state"] == "waiting"
    assert row["attention_reason"] == "takeover"
    assert row["takeover_run_id"] == run_id
    stopped = client.post(f"/v1/threads/{bot_id}/stop", headers=auth_header)
    assert stopped.status_code == 200, stopped.text
    wait_run(client, auth_header, bot_id, run_id)


def test_previous_result_id_remains_when_new_work_starts(client, auth_header) -> None:
    bot_id = create_bot(client, auth_header, "OverlapToday")["id"]
    first = client.post(
        f"/v1/threads/{bot_id}/messages",
        headers=auth_header,
        json={"text": "please e2e-no-questions"},
    )
    assert first.status_code == 200
    done = wait_run(client, auth_header, bot_id, first.json()["run_id"])
    first_id = done["run"]["id"]
    unread = client.post(f"/v1/threads/{bot_id}/unread", headers=auth_header)
    assert unread.status_code == 200
    second = client.post(
        f"/v1/threads/{bot_id}/messages",
        headers=auth_header,
        json={"text": "please e2e-slow now"},
    )
    assert second.status_code == 200
    wait_run_status(client, auth_header, bot_id, second.json()["run_id"], "running")
    row = _bot_row(client, auth_header, bot_id)
    assert row["execution_state"] == "running"
    assert row["result_id"] == first_id
    assert row["result_id"] != second.json()["run_id"]
    stopped = client.post(f"/v1/threads/{bot_id}/stop", headers=auth_header)
    assert stopped.status_code == 200, stopped.text
    wait_run(client, auth_header, bot_id, second.json()["run_id"])


def test_late_list_snapshot_does_not_undo_accepted_decision(client, auth_header) -> None:
    bot_id = create_bot(client, auth_header, "StaleToday")["id"]
    sent = client.post(
        f"/v1/threads/{bot_id}/messages",
        headers=auth_header,
        json={"text": "e2e-consent-browse"},
    )
    assert sent.status_code == 200
    run_id = sent.json()["run_id"]
    snap = wait_run_status(client, auth_header, bot_id, run_id, "waiting_input")
    stale = client.app.state.store.get_bot(bot_id)
    assert stale is not None
    assert stale.attention_reason == "approval"
    consent_id = consent_id_from_thread(snap)
    allowed = client.post(
        f"/v1/consents/{consent_id}",
        headers=auth_header,
        json={"decision": "allow"},
    )
    assert allowed.status_code == 200, allowed.text
    wait_run(client, auth_header, bot_id, run_id)
    current = client.app.state.store.get_bot(bot_id)
    assert current is not None
    assert current.attention_reason == "none"
    merged = merge_bot_projection(current, stale)
    assert merged.attention_reason == "none"
    assert merged.state_version == current.state_version
    assert merged.pending_consent_id is None
