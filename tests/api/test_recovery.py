from __future__ import annotations

from tests.api.helpers import (
    consent_id_from_thread,
    create_bot,
    simulate_host_restart,
    wait_pending_auto_jobs,
    wait_run,
    wait_run_status,
    wait_thread_has,
)


def _recovery_blocks(payload: dict) -> list[dict]:
    found: list[dict] = []
    for msg in payload.get("messages") or []:
        for block in msg.get("blocks") or []:
            if block.get("kind") == "recovery":
                found.append({"message": msg, "block": block})
    return found


def _pending_ask(payload: dict) -> tuple[dict, dict]:
    pending = [
        (message, block)
        for message in payload.get("messages") or []
        for block in message.get("blocks") or []
        if block.get("kind") == "ask"
        and block.get("status") == "pending"
        and not block.get("consent_id")
    ]
    assert len(pending) == 1
    return pending[0]


def test_recovered_ask_answer_reaches_followup_prompt(client, auth_header, monkeypatch) -> None:
    from artek_buddy.http import turns
    from artek_buddy.runtime.types import RunRecord

    bot_id = create_bot(client, auth_header, "RecoverAskPrompt")["id"]
    sent = client.post(
        f"/v1/threads/{bot_id}/messages",
        headers=auth_header,
        json={"text": "please e2e-blocked-browser"},
    )
    assert sent.status_code == 200
    run_id = sent.json()["run_id"]
    waiting = wait_run_status(client, auth_header, bot_id, run_id, "waiting_input")
    message, _block = _pending_ask(waiting)

    simulate_host_restart(client)
    captured: list[str] = []

    async def capture(history, rt, prompt, agent_id, bot, **kwargs):
        captured.append(prompt)
        yield RunRecord(
            id="run_audit_projection",
            agent_id=agent_id,
            status="completed",
            result="audit projection finished",
        )

    monkeypatch.setattr(turns, "_turn_stream", capture)
    canary = "unique-owner-answer-emerald-4729"
    answered = client.post(
        f"/v1/threads/{bot_id}/answer",
        headers=auth_header,
        json={"run_id": run_id, "message_id": message["id"], "answer": canary},
    )
    assert answered.status_code == 200, answered.text
    wait_thread_has(client, auth_header, bot_id, "audit projection finished")
    assert len(captured) == 1
    assert canary in captured[0]


def test_restart_during_ask_keeps_thread_and_answer_continues(client, auth_header) -> None:
    bot_id = create_bot(client, auth_header, "RecoverAsk")["id"]
    sent = client.post(
        f"/v1/threads/{bot_id}/messages",
        headers=auth_header,
        json={"text": "please e2e-blocked-browser"},
    )
    assert sent.status_code == 200
    run_id = sent.json()["run_id"]
    waiting = wait_run_status(client, auth_header, bot_id, run_id, "waiting_input")
    message, _block = _pending_ask(waiting)
    assert not _recovery_blocks(waiting)

    simulate_host_restart(client)
    after = client.get(f"/v1/threads/{bot_id}", headers=auth_header)
    assert after.status_code == 200
    body = after.json()
    assert body["run"]["id"] == run_id
    assert body["run"]["status"] == "waiting_input"
    assert body["run"]["status"] != "failed"
    assert not _recovery_blocks(body)
    message, _block = _pending_ask(body)

    answered = client.post(
        f"/v1/threads/{bot_id}/answer",
        headers=auth_header,
        json={
            "run_id": run_id,
            "message_id": message["id"],
            "answer": "I completed the step",
        },
    )
    assert answered.status_code == 200, answered.text
    finished = wait_run(client, auth_header, bot_id, run_id)
    assert finished["run"]["status"] == "completed"
    wait_thread_has(client, auth_header, bot_id, "ok")
    listed = client.get("/v1/bots", headers=auth_header).json()["bots"]
    row = next(item for item in listed if item["id"] == bot_id)
    assert row["attention_reason"] != "recovery"


def test_restart_during_interactive_consent_allow_continues(client, auth_header) -> None:
    bot_id = create_bot(client, auth_header, "RecoverConsent")["id"]
    sent = client.post(
        f"/v1/threads/{bot_id}/messages",
        headers=auth_header,
        json={"text": "e2e-consent-browse"},
    )
    assert sent.status_code == 200
    run_id = sent.json()["run_id"]
    waiting = wait_run_status(client, auth_header, bot_id, run_id, "waiting_input")
    consent_id = consent_id_from_thread(waiting)
    assert not _recovery_blocks(waiting)

    simulate_host_restart(client)
    after = client.get(f"/v1/threads/{bot_id}", headers=auth_header)
    assert after.status_code == 200
    body = after.json()
    assert body["run"]["id"] == run_id
    assert body["run"]["status"] == "waiting_input"
    assert body["run"]["status"] != "failed"
    assert not _recovery_blocks(body)

    allowed = client.post(
        f"/v1/consents/{consent_id}",
        headers=auth_header,
        json={"decision": "allow"},
    )
    assert allowed.status_code == 200, allowed.text
    finished = wait_run(client, auth_header, bot_id, run_id)
    assert finished["run"]["status"] == "completed"
    wait_thread_has(client, auth_header, bot_id, "ok")


def test_restart_during_interactive_consent_deny_terminates(client, auth_header) -> None:
    bot_id = create_bot(client, auth_header, "RecoverConsentDeny")["id"]
    sent = client.post(
        f"/v1/threads/{bot_id}/messages",
        headers=auth_header,
        json={"text": "e2e-consent-browse"},
    )
    assert sent.status_code == 200
    run_id = sent.json()["run_id"]
    waiting = wait_run_status(client, auth_header, bot_id, run_id, "waiting_input")
    consent_id = consent_id_from_thread(waiting)

    simulate_host_restart(client)
    denied = client.post(
        f"/v1/consents/{consent_id}",
        headers=auth_header,
        json={"decision": "deny"},
    )
    assert denied.status_code == 200, denied.text
    finished = wait_run(client, auth_header, bot_id, run_id)
    assert finished["run"]["status"] == "failed"
    assert client.app.state.store.get_consent_request(consent_id).status == "deny"


def test_recovery_rejects_card_from_another_bot(client, auth_header) -> None:
    store = client.app.state.store
    bot_a_id = create_bot(client, auth_header, "Recovery A")["id"]
    bot_b_id = create_bot(client, auth_header, "Recovery B")["id"]

    def _park_slow(bot_id: str) -> tuple[str, str]:
        sent = client.post(
            f"/v1/threads/{bot_id}/messages",
            headers=auth_header,
            json={"text": "please e2e-slow now"},
        )
        assert sent.status_code == 200
        run_id = sent.json()["run_id"]
        wait_run_status(client, auth_header, bot_id, run_id, "running")
        simulate_host_restart(client)
        snap = client.get(f"/v1/threads/{bot_id}", headers=auth_header).json()
        assert snap["run"]["status"] == "waiting_recovery"
        cards = _recovery_blocks(snap)
        assert len(cards) == 1
        return run_id, cards[0]["message"]["id"]

    run_a_id, _card_a = _park_slow(bot_a_id)
    run_b_id, card_b_id = _park_slow(bot_b_id)

    response = client.post(
        f"/v1/threads/{bot_a_id}/recovery",
        headers=auth_header,
        json={
            "run_id": run_a_id,
            "message_id": card_b_id,
            "action": "new_attempt",
        },
    )
    assert response.status_code == 409, response.text
    assert store.get_run(run_a_id).status == "waiting_recovery"
    assert store.get_run(run_b_id).status == "waiting_recovery"
    wait_b = store.get_run_wait(run_b_id)
    assert wait_b is not None and wait_b.message_id == card_b_id
    msg_b = store.get_message_in_thread(store.get_bot(bot_b_id).thread_id, card_b_id)
    block = next(b for b in msg_b.blocks if getattr(b, "kind", None) == "recovery")
    assert getattr(block, "status", None) == "pending"


def test_restart_during_running_is_check_not_failed(client, auth_header) -> None:
    bot_id = create_bot(client, auth_header, "RecoverCheck")["id"]
    sent = client.post(
        f"/v1/threads/{bot_id}/messages",
        headers=auth_header,
        json={"text": "please e2e-slow now"},
    )
    assert sent.status_code == 200
    run_id = sent.json()["run_id"]
    wait_run_status(client, auth_header, bot_id, run_id, "running")

    simulate_host_restart(client)
    after = client.get(f"/v1/threads/{bot_id}", headers=auth_header)
    assert after.status_code == 200
    body = after.json()
    assert body["run"]["id"] == run_id
    assert body["run"]["status"] == "waiting_recovery"
    assert body["run"]["recovery_path"] == "check"
    cards = _recovery_blocks(body)
    assert len(cards) == 1
    block = cards[0]["block"]
    assert block["path"] == "check"
    assert block["status"] == "pending"
    action_ids = [item["id"] for item in block.get("actions") or []]
    assert "continue" not in action_ids
    assert "new_attempt" in action_ids
    listed = client.get("/v1/bots", headers=auth_header).json()["bots"]
    row = next(item for item in listed if item["id"] == bot_id)
    assert row["attention_reason"] == "recovery"
    assert row["pending_recovery_id"] == cards[0]["message"]["id"]
    assert row["execution_state"] == "waiting"

    denied = client.post(
        f"/v1/threads/{bot_id}/recovery",
        headers=auth_header,
        json={
            "run_id": run_id,
            "message_id": cards[0]["message"]["id"],
            "action": "continue",
        },
    )
    assert denied.status_code == 409

    recovered = client.post(
        f"/v1/threads/{bot_id}/recovery",
        headers=auth_header,
        json={
            "run_id": run_id,
            "message_id": cards[0]["message"]["id"],
            "action": "new_attempt",
        },
    )
    assert recovered.status_code == 200, recovered.text
    parked = client.get(f"/v1/threads/{bot_id}", headers=auth_header).json()
    assert parked["run"]["id"] == run_id
    assert parked["run"]["status"] == "cancelled"
    resolved = _recovery_blocks(parked)
    assert resolved[0]["block"]["status"] == "resolved"


def test_restart_does_not_execute_owner_job_twice(client, auth_header) -> None:
    bot_id = create_bot(client, auth_header, "RecoverJob")["id"]
    sent = client.post(
        f"/v1/threads/{bot_id}/messages",
        headers=auth_header,
        json={"text": "e2e-consent-auto-read"},
    )
    assert sent.status_code == 200
    run_id = sent.json()["run_id"]
    waiting = wait_pending_auto_jobs(client, auth_header, bot_id)
    consent_id = waiting["pending_auto_consent_id"]
    assert consent_id
    wait_run_status(client, auth_header, bot_id, run_id, "waiting_input")

    simulate_host_restart(client)
    job = client.get(f"/v1/consents/{consent_id}", headers=auth_header)
    assert job.status_code == 200
    assert job.json()["job_status"] == "failed"
    ack = client.post(f"/v1/consents/{consent_id}/ack", headers=auth_header)
    assert ack.status_code == 409
    result = client.post(
        f"/v1/consents/{consent_id}/result",
        headers=auth_header,
        json={"ok": True, "text": "should not land"},
    )
    assert result.status_code == 409
    after = client.get(f"/v1/threads/{bot_id}", headers=auth_header).json()
    assert after["run"]["status"] == "waiting_recovery"
    assert after["run"]["recovery_path"] == "new_attempt"
    cards = _recovery_blocks(after)
    assert len(cards) == 1
    assert cards[0]["block"]["path"] == "new_attempt"
    assert "continue" not in [item["id"] for item in cards[0]["block"].get("actions") or []]


def test_late_finish_turn_after_recover_does_not_complete(client, auth_header) -> None:
    bot_id = create_bot(client, auth_header, "RecoverLate")["id"]
    sent = client.post(
        f"/v1/threads/{bot_id}/messages",
        headers=auth_header,
        json={"text": "please e2e-slow now"},
    )
    assert sent.status_code == 200
    run_id = sent.json()["run_id"]
    wait_run_status(client, auth_header, bot_id, run_id, "running")
    simulate_host_restart(client)
    store = client.app.state.store
    bot = store.get_bot(bot_id)
    run = store.get_run(run_id)
    assert bot is not None and run is not None
    store.finish_turn(bot, run, "late complete from dead worker", "completed")
    live = store.get_run(run_id)
    assert live is not None
    assert live.status == "waiting_recovery"
    snap = client.get(f"/v1/threads/{bot_id}", headers=auth_header).json()
    assert snap["run"]["status"] == "waiting_recovery"
    blob = " ".join(
        str(block.get("text") or "")
        for msg in snap["messages"]
        for block in msg.get("blocks") or []
    )
    assert "late complete from dead worker" not in blob


def test_restart_during_takeover_is_new_attempt(client, auth_header) -> None:
    bot_id = create_bot(client, auth_header, "RecoverTakeover")["id"]
    sent = client.post(
        f"/v1/threads/{bot_id}/messages",
        headers=auth_header,
        json={"text": "please e2e-park-takeover"},
    )
    assert sent.status_code == 200
    run_id = sent.json()["run_id"]
    wait_run_status(client, auth_header, bot_id, run_id, "waiting_takeover")
    simulate_host_restart(client)
    after = client.get(f"/v1/threads/{bot_id}", headers=auth_header).json()
    assert after["run"]["status"] == "waiting_recovery"
    assert after["run"]["recovery_path"] == "new_attempt"
    cards = _recovery_blocks(after)
    assert len(cards) == 1
    assert cards[0]["block"]["path"] == "new_attempt"
    assert "continue" not in [item["id"] for item in cards[0]["block"].get("actions") or []]
