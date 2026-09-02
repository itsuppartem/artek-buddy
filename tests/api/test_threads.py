from __future__ import annotations

import time

from tests.api.helpers import (
    create_bot,
    message_texts,
    wait_pending_auto_jobs,
    wait_run,
    wait_run_status,
    wait_thread_has,
)


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


def test_completed_event_carries_only_the_new_final_message(client, auth_header) -> None:
    bot_id = create_bot(client, auth_header, "NotifyFinal")["id"]
    sent = client.post(
        f"/v1/threads/{bot_id}/messages",
        headers=auth_header,
        json={"text": "hello"},
    )
    assert sent.status_code == 200
    run_id = sent.json()["run_id"]
    wait_run(client, auth_header, bot_id, run_id)
    completed = [
        event
        for event in client.app.state.hub.replay(bot_id)
        if event.type.value == "run.completed" and event.run_id == run_id
    ]
    assert len(completed) == 1
    message = completed[0].payload["message"]
    assert message["role"] == "bot"
    assert any(
        block.get("kind") == "text" and block.get("text") == "ok" for block in message["blocks"]
    )


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
    assert snap["run"].get("error") == "scripted fail"
    assert "run failed: run-" not in (snap["run"].get("error") or "")
    assert "scripted fail" not in message_texts(snap)


def test_scripted_turn_fail_raw_id_is_human(client, auth_header) -> None:
    from artek_buddy.db.shaping import TURN_FAILED
    from artek_buddy.runtime.scripted import E2E_FAIL_RAW_ERROR

    bot_id = create_bot(client, auth_header, "ScriptedFailRaw")["id"]
    sent = client.post(
        f"/v1/threads/{bot_id}/messages",
        headers=auth_header,
        json={"text": "please e2e-fail-raw now"},
    )
    assert sent.status_code == 200
    snap = wait_run(client, auth_header, bot_id, sent.json()["run_id"])
    assert snap["run"]["status"] == "failed"
    assert snap["run"].get("error") == TURN_FAILED
    assert E2E_FAIL_RAW_ERROR not in (snap["run"].get("error") or "")
    blob = "\n".join(message_texts(snap))
    assert "run failed: run-" not in blob
    assert E2E_FAIL_RAW_ERROR not in blob


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


def _last_prompt() -> str:
    from artek_buddy.main import app

    runtime = getattr(app.state, "runtime", None)
    return str(getattr(runtime, "last_prompt", None) or "")


def test_stop_does_not_complete_cancelled_body(client, auth_header) -> None:
    from artek_buddy.runtime.scripted import E2E_SLOW_ANSWER

    bot_id = create_bot(client, auth_header, "StopBody")["id"]
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
    assert E2E_SLOW_ANSWER not in message_texts(snap)
    time.sleep(3)
    later = client.get(f"/v1/threads/{bot_id}", headers=auth_header)
    assert later.status_code == 200
    assert later.json()["run"]["status"] == "cancelled"
    assert E2E_SLOW_ANSWER not in message_texts(later.json())


def test_stop_late_complete_shows_stopped_and_drops_model_text(client, auth_header) -> None:
    from artek_buddy.runtime.scripted import E2E_LATE_COMPLETE

    bot_id = create_bot(client, auth_header, "StopLate")["id"]
    sent = client.post(
        f"/v1/threads/{bot_id}/messages",
        headers=auth_header,
        json={"text": "please e2e-late-complete"},
    )
    assert sent.status_code == 200
    run_id = sent.json()["run_id"]
    stopped = client.post(f"/v1/threads/{bot_id}/stop", headers=auth_header)
    assert stopped.status_code == 200
    snap = wait_run(client, auth_header, bot_id, run_id)
    assert snap["run"]["status"] == "cancelled"
    assert snap["run"]["error"] == "Stopped."
    assert E2E_LATE_COMPLETE not in message_texts(snap)
    time.sleep(3)
    later = client.get(f"/v1/threads/{bot_id}", headers=auth_header)
    assert later.status_code == 200
    assert later.json()["run"]["status"] == "cancelled"
    assert later.json()["run"]["error"] == "Stopped."
    assert E2E_LATE_COMPLETE not in message_texts(later.json())


def test_e2e_takeover_parks_waiting_takeover(client, auth_header) -> None:
    bot_id = create_bot(client, auth_header, "TakeoverPark")["id"]
    parked = client.post(
        f"/v1/threads/{bot_id}/messages",
        headers=auth_header,
        json={"text": "please e2e-takeover"},
    )
    assert parked.status_code == 200
    run_id = parked.json()["run_id"]
    snap = wait_run_status(client, auth_header, bot_id, run_id, "waiting_takeover")
    assert snap["run"]["status"] == "waiting_takeover"
    listed = client.get(f"/v1/bots/{bot_id}", headers=auth_header)
    assert listed.status_code == 200
    assert listed.json()["status"] == "waiting_takeover"
    assert "need you" not in message_texts(snap)


def test_send_while_waiting_takeover_starts_turn(client, auth_header) -> None:
    bot_id = create_bot(client, auth_header, "TakeoverSend")["id"]
    parked = client.post(
        f"/v1/threads/{bot_id}/messages",
        headers=auth_header,
        json={"text": "please e2e-park-takeover"},
    )
    assert parked.status_code == 200
    run_id = parked.json()["run_id"]
    wait_run_status(client, auth_header, bot_id, run_id, "waiting_takeover")
    queued_park = client.post(
        f"/v1/threads/{bot_id}/messages",
        headers=auth_header,
        json={"text": "please e2e-slow now"},
    )
    assert queued_park.status_code == 200
    payload = queued_park.json()
    assert payload.get("queued") is not True
    new_run = payload["run_id"]
    assert new_run != run_id
    behind = client.post(
        f"/v1/threads/{bot_id}/messages",
        headers=auth_header,
        json={"text": "while the new run is live"},
    )
    assert behind.status_code == 200
    assert behind.json().get("queued") is True
    deadline = time.time() + 15
    last: dict = {}
    while time.time() < deadline:
        response = client.get(f"/v1/threads/{bot_id}", headers=auth_header)
        assert response.status_code == 200
        last = response.json()
        run = last.get("run") or {}
        if run.get("trigger") == "follow_up" and run.get("status") in {
            "completed",
            "failed",
            "cancelled",
        }:
            break
        time.sleep(0.1)
    else:
        raise AssertionError(
            f"queued follow-up did not finish after takeover send: {last.get('run')}"
        )
    assert last["run"]["id"] != run_id
    assert last["run"]["status"] != "waiting_takeover"
    assert "while the new run is live" in message_texts(last)


def test_stop_keeps_queued_owner_lines_on_next_send(client, auth_header) -> None:
    bot_id = create_bot(client, auth_header, "KeepInbox")["id"]
    before = client.get(f"/v1/computer/{bot_id}", headers=auth_header)
    assert before.status_code == 200
    sent = client.post(
        f"/v1/threads/{bot_id}/messages",
        headers=auth_header,
        json={"text": "please e2e-slow now"},
    )
    assert sent.status_code == 200
    first = client.post(
        f"/v1/threads/{bot_id}/messages",
        headers=auth_header,
        json={"text": "count the foxes on the desk"},
    )
    assert first.status_code == 200
    assert first.json().get("queued") is True
    second = client.post(
        f"/v1/threads/{bot_id}/messages",
        headers=auth_header,
        json={"text": "also note the red one"},
    )
    assert second.status_code == 200
    assert second.json().get("queued") is True
    stopped = client.post(f"/v1/threads/{bot_id}/stop", headers=auth_header)
    assert stopped.status_code == 200
    after_stop = client.get(f"/v1/computer/{bot_id}", headers=auth_header)
    assert after_stop.status_code == 200
    assert after_stop.json()["state"] == before.json()["state"]
    follow = client.post(
        f"/v1/threads/{bot_id}/messages",
        headers=auth_header,
        json={"text": "continue"},
    )
    assert follow.status_code == 200
    assert follow.json().get("queued") is not True
    wait_run(client, auth_header, bot_id, follow.json()["run_id"])
    prompt = _last_prompt()
    assert "count the foxes on the desk" in prompt
    assert "also note the red one" in prompt
    assert prompt.strip() != "continue"


def test_turn_prompt_includes_thread_not_only_last_line(client, auth_header) -> None:
    bot_id = create_bot(client, auth_header, "ThreadCtx")["id"]
    first = client.post(
        f"/v1/threads/{bot_id}/messages",
        headers=auth_header,
        json={"text": "the fox count is seven"},
    )
    assert first.status_code == 200
    wait_run(client, auth_header, bot_id, first.json()["run_id"])
    follow = client.post(
        f"/v1/threads/{bot_id}/messages",
        headers=auth_header,
        json={"text": "continue"},
    )
    assert follow.status_code == 200
    wait_run(client, auth_header, bot_id, follow.json()["run_id"])
    prompt = _last_prompt()
    assert "the fox count is seven" in prompt
    assert prompt.strip() != "continue"


def test_new_session_gets_one_resume_brief_from_existing_thread(client, auth_header) -> None:
    from artek_buddy.main import app

    bot_id = create_bot(client, auth_header, "ResumeBrief")["id"]
    first = client.post(
        f"/v1/threads/{bot_id}/messages",
        headers=auth_header,
        json={"text": "the current branch is feature/rpc"},
    )
    assert first.status_code == 200
    wait_run(client, auth_header, bot_id, first.json()["run_id"])
    bot = app.state.store.get_bot(bot_id)
    assert bot is not None
    assert bot.cursor_agent_id
    app.state.runtime.mark_session_fresh(bot.cursor_agent_id)

    resumed = client.post(
        f"/v1/threads/{bot_id}/messages",
        headers=auth_header,
        json={"text": "continue"},
    )
    assert resumed.status_code == 200
    wait_run(client, auth_header, bot_id, resumed.json()["run_id"])
    prompt = _last_prompt()
    assert "<session_resume>" in prompt
    assert "tool history from the replaced session is unavailable" in prompt
    assert "the current branch is feature/rpc" in prompt

    next_turn = client.post(
        f"/v1/threads/{bot_id}/messages",
        headers=auth_header,
        json={"text": "continue once more"},
    )
    assert next_turn.status_code == 200
    wait_run(client, auth_header, bot_id, next_turn.json()["run_id"])
    assert "<session_resume>" not in _last_prompt()


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
    assert body["job_status"] == "queued"
    uploaded = client.post(
        f"/v1/consents/{pending}/file",
        headers=auth_header,
        json={"name": "notes.txt", "text": "notes from owner"},
    )
    assert uploaded.status_code == 200
    finished = wait_run(client, auth_header, bot_id, run_id)
    assert finished["run"]["status"] == "completed"
    completed = client.get(f"/v1/consents/{pending}", headers=auth_header)
    assert completed.status_code == 200
    assert completed.json()["job_status"] == "completed"


def test_ask_user_answer_resumes_the_same_run_once(client, auth_header) -> None:
    bot_id = create_bot(client, auth_header, "OwnerHelp")["id"]
    sent = client.post(
        f"/v1/threads/{bot_id}/messages",
        headers=auth_header,
        json={"text": "please e2e-blocked-browser"},
    )
    assert sent.status_code == 200
    run_id = sent.json()["run_id"]
    waiting = wait_run_status(client, auth_header, bot_id, run_id, "waiting_input", timeout=5)
    pending = [
        (message, block)
        for message in waiting["messages"]
        for block in message["blocks"]
        if block.get("kind") == "ask"
        and block.get("status") == "pending"
        and not block.get("consent_id")
    ]
    assert len(pending) == 1
    message, _block = pending[0]

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
    duplicate = client.post(
        f"/v1/threads/{bot_id}/answer",
        headers=auth_header,
        json={
            "run_id": run_id,
            "message_id": message["id"],
            "answer": "second answer",
        },
    )
    assert duplicate.status_code == 409

    finished = wait_run(client, auth_header, bot_id, run_id)
    assert finished["run"]["id"] == run_id
    assert finished["run"]["status"] == "completed"
    answered_message = next(item for item in finished["messages"] if item["id"] == message["id"])
    answered_block = next(
        block for block in answered_message["blocks"] if block.get("kind") == "ask"
    )
    assert answered_block["status"] == "answered"
    assert answered_block["answer"] == "I completed the step"
    assert any(
        block.get("kind") == "text" and "continued after your help" in block.get("text", "")
        for item in finished["messages"]
        for block in item["blocks"]
    )


def test_thread_snapshot_exposes_every_pending_auto_owner_job(client, auth_header) -> None:
    bot_id = create_bot(client, auth_header, "ParallelAutoRead")["id"]
    sent = client.post(
        f"/v1/threads/{bot_id}/messages",
        headers=auth_header,
        json={"text": "e2e-consent-auto-read"},
    )
    assert sent.status_code == 200
    run_id = sent.json()["run_id"]
    waiting = wait_run_status(client, auth_header, bot_id, run_id, "waiting_input", timeout=5)
    first_id = waiting["pending_auto_consent_id"]
    assert first_id

    store = client.app.state.store
    bot = store.get_bot(bot_id)
    assert bot is not None
    second_id = "cns_parallel_snapshot"
    store.create_consent_request(
        second_id,
        bot_id=bot_id,
        run_id=run_id,
        thread_id=bot.thread_id,
        message_id=None,
        action_class="owner_read",
        scope_key="~",
        summary="List ~ on your computer?",
        workspace_id=bot.workspace_id,
        job_status="queued",
    )

    snapshot = client.get(f"/v1/threads/{bot_id}", headers=auth_header)
    assert snapshot.status_code == 200
    assert set(snapshot.json()["pending_auto_consent_ids"]) == {first_id, second_id}
    assert store.finish_consent_job(second_id, "completed")
    uploaded = client.post(
        f"/v1/consents/{first_id}/result",
        headers=auth_header,
        json={"ok": True, "text": "notes from owner"},
    )
    assert uploaded.status_code == 200
    assert wait_run(client, auth_header, bot_id, run_id)["run"]["status"] == "completed"


def test_worker_auto_owner_job_survives_thread_reload(client, auth_header) -> None:
    """A worker This-PC read must remain on snapshot after the lead run completes (#361)."""
    from artek_buddy.runtime.scripted import E2E_WORKER_ACK

    bot_id = create_bot(client, auth_header, "WorkerAutoReload")["id"]
    sent = client.post(
        f"/v1/threads/{bot_id}/messages",
        headers=auth_header,
        json={"text": "please e2e-worker-auto-read"},
    )
    assert sent.status_code == 200
    run_id = sent.json()["run_id"]
    lead = wait_run(client, auth_header, bot_id, run_id)
    assert lead["run"]["status"] == "completed"
    assert E2E_WORKER_ACK in message_texts(lead)

    snap = wait_pending_auto_jobs(client, auth_header, bot_id)
    consent_id = snap["pending_auto_consent_id"]
    assert consent_id
    assert consent_id in snap["pending_auto_consent_ids"]
    job = client.get(f"/v1/consents/{consent_id}", headers=auth_header)
    assert job.status_code == 200
    body = job.json()
    assert body["action_class"] == "owner_read"
    assert body["job_status"] == "queued"
    stored = client.app.state.store.get_consent_request(consent_id)
    assert stored is not None
    assert stored.run_id != run_id
    assert stored.parent_run_id == run_id

    claimed = client.post(
        f"/v1/consents/{consent_id}/ack",
        headers=auth_header,
        json={"claim_capable": True},
    )
    assert claimed.status_code == 200
    claim = claimed.json().get("claim")
    assert isinstance(claim, str) and claim
    duplicate = client.post(f"/v1/consents/{consent_id}/ack", headers=auth_header)
    assert duplicate.status_code == 409
    loser = client.post(
        f"/v1/consents/{consent_id}/result",
        headers=auth_header,
        json={"ok": False, "error": "no paired client"},
    )
    assert loser.status_code == 409
    uploaded = client.post(
        f"/v1/consents/{consent_id}/file",
        headers=auth_header,
        json={"name": "notes.txt", "text": "notes from owner", "claim": claim},
    )
    assert uploaded.status_code == 200
    done = wait_thread_has(client, auth_header, bot_id, "got notes")
    assert any(item.get("status") == "completed" for item in done.get("subagents") or [])
    finished = client.get(f"/v1/consents/{consent_id}", headers=auth_header)
    assert finished.status_code == 200
    assert finished.json()["job_status"] == "completed"
    final_snap = client.get(f"/v1/threads/{bot_id}", headers=auth_header)
    assert final_snap.status_code == 200
    assert final_snap.json()["pending_auto_consent_id"] is None


def test_auto_owner_job_ack_is_single_claim_and_rejects_loser_result(client, auth_header) -> None:
    bot_id = create_bot(client, auth_header, "AutoAck")["id"]
    sent = client.post(
        f"/v1/threads/{bot_id}/messages",
        headers=auth_header,
        json={"text": "e2e-consent-auto-read"},
    )
    assert sent.status_code == 200
    run_id = sent.json()["run_id"]
    snap = wait_run_status(client, auth_header, bot_id, run_id, "waiting_input", timeout=5)
    consent_id = snap["pending_auto_consent_id"]
    assert consent_id

    claimed = client.post(
        f"/v1/consents/{consent_id}/ack",
        headers=auth_header,
        json={"claim_capable": True},
    )
    assert claimed.status_code == 200
    claim = claimed.json().get("claim")
    assert isinstance(claim, str) and claim
    duplicate = client.post(f"/v1/consents/{consent_id}/ack", headers=auth_header)
    assert duplicate.status_code == 409
    acknowledged = client.get(f"/v1/consents/{consent_id}", headers=auth_header)
    assert acknowledged.status_code == 200
    assert acknowledged.json()["job_status"] == "acknowledged"

    loser = client.post(
        f"/v1/consents/{consent_id}/result",
        headers=auth_header,
        json={"ok": False, "error": "owner read failed"},
    )
    assert loser.status_code == 409
    uploaded = client.post(
        f"/v1/consents/{consent_id}/result",
        headers=auth_header,
        json={"ok": True, "text": "notes from owner", "claim": claim},
    )
    assert uploaded.status_code == 200

    finished = wait_run(client, auth_header, bot_id, run_id)
    assert finished["run"]["status"] == "completed"
    final_snap = client.get(f"/v1/threads/{bot_id}", headers=auth_header)
    assert final_snap.status_code == 200
    assert final_snap.json()["pending_auto_consent_id"] is None


def _computer_blocks(payload: dict) -> list[dict]:
    found: list[dict] = []
    for msg in payload.get("messages") or []:
        for block in msg.get("blocks") or []:
            if block.get("kind") == "computer":
                found.append(block)
    return found


def test_request_takeover_with_reason_release_resumes_same_run(client, auth_header) -> None:
    from artek_buddy.runtime.scripted import E2E_TAKEOVER_REASON

    bot_id = create_bot(client, auth_header, "ResumeDesk")["id"]
    parked = client.post(
        f"/v1/threads/{bot_id}/messages",
        headers=auth_header,
        json={"text": "please e2e-park-takeover"},
    )
    assert parked.status_code == 200
    run_id = parked.json()["run_id"]
    waiting = wait_run_status(client, auth_header, bot_id, run_id, "waiting_takeover")
    cards = _computer_blocks(waiting)
    assert cards
    assert E2E_TAKEOVER_REASON in cards[-1]["text"]
    released = client.post(f"/v1/computer/{bot_id}/release", headers=auth_header)
    assert released.status_code == 200
    done = wait_run(client, auth_header, bot_id, run_id)
    assert done["run"]["id"] == run_id
    assert done["run"]["status"] == "completed"
    assert "continuing after takeover" in message_texts(done)


def test_stop_from_waiting_takeover_cancels_and_release_does_not_resume(
    client, auth_header
) -> None:
    bot_id = create_bot(client, auth_header, "StopPark")["id"]
    parked = client.post(
        f"/v1/threads/{bot_id}/messages",
        headers=auth_header,
        json={"text": "please e2e-park-takeover"},
    )
    assert parked.status_code == 200
    run_id = parked.json()["run_id"]
    wait_run_status(client, auth_header, bot_id, run_id, "waiting_takeover")
    stopped = client.post(f"/v1/threads/{bot_id}/stop", headers=auth_header)
    assert stopped.status_code == 200
    snap = wait_run(client, auth_header, bot_id, run_id)
    assert snap["run"]["status"] == "cancelled"
    released = client.post(f"/v1/computer/{bot_id}/release", headers=auth_header)
    assert released.status_code == 200
    later = client.get(f"/v1/threads/{bot_id}", headers=auth_header)
    assert later.status_code == 200
    assert later.json()["run"]["id"] == run_id
    assert later.json()["run"]["status"] == "cancelled"
    assert "continuing after takeover" not in message_texts(later.json())


def test_empty_takeover_reason_is_defaulted(client, auth_header) -> None:
    from artek_buddy.main import app
    from artek_buddy.runtime.tools import ProductTools

    bot_id = create_bot(client, auth_header, "EmptyReason")["id"]
    parked = client.post(
        f"/v1/threads/{bot_id}/messages",
        headers=auth_header,
        json={"text": "please e2e-park-takeover"},
    )
    assert parked.status_code == 200
    run_id = parked.json()["run_id"]
    wait_run_status(client, auth_header, bot_id, run_id, "waiting_takeover")
    bot = app.state.store.get_bot(bot_id)
    assert bot is not None
    app.state.runtime.set_current_turn_context(bot_id, run_id, bot.thread_id)
    out = ProductTools(app.state.runtime).execute("request_takeover", {}, bound_bot_id=bot_id)
    assert out["ok"] is True
    assert str(out.get("reason") or "").strip()


def test_cursor_auth_error_recycle_after_n_failures(client, auth_header) -> None:
    from artek_buddy.main import app
    from artek_buddy.runtime.cursor_wait import CURSOR_AUTH_RECYCLE_AFTER
    from artek_buddy.runtime.scripted import E2E_AUTH_ERROR

    bot_id = create_bot(client, auth_header, "AuthDead")["id"]
    assert app.state.runtime.bridge_recycles == 0
    last_run = ""
    for _ in range(CURSOR_AUTH_RECYCLE_AFTER):
        sent = client.post(
            f"/v1/threads/{bot_id}/messages",
            headers=auth_header,
            json={"text": "please e2e-auth-error"},
        )
        assert sent.status_code == 200
        last_run = sent.json()["run_id"]
        snap = wait_run(client, auth_header, bot_id, last_run)
        assert snap["run"]["status"] == "failed"
        assert E2E_AUTH_ERROR in (snap["run"].get("error") or "")
        assert f"run failed: {last_run}" != (snap["run"].get("error") or "")
    assert app.state.runtime.bridge_recycles == 1
    nxt = client.post(
        f"/v1/threads/{bot_id}/messages",
        headers=auth_header,
        json={"text": "please e2e-auth-error"},
    )
    assert nxt.status_code == 200
    done = wait_run(client, auth_header, bot_id, nxt.json()["run_id"])
    assert done["run"]["status"] == "completed"
    assert "recovered" in message_texts(done)


def test_single_auth_error_does_not_recycle_the_bridge(client, auth_header) -> None:
    from artek_buddy.main import app
    from artek_buddy.runtime.scripted import E2E_AUTH_ERROR

    bot_id = create_bot(client, auth_header, "AuthOnce")["id"]
    sent = client.post(
        f"/v1/threads/{bot_id}/messages",
        headers=auth_header,
        json={"text": "please e2e-auth-error"},
    )
    assert sent.status_code == 200
    snap = wait_run(client, auth_header, bot_id, sent.json()["run_id"])
    assert snap["run"]["status"] == "failed"
    assert E2E_AUTH_ERROR in (snap["run"].get("error") or "")
    assert app.state.runtime.bridge_recycles == 0
    nxt = client.post(
        f"/v1/threads/{bot_id}/messages",
        headers=auth_header,
        json={"text": "hello"},
    )
    assert nxt.status_code == 200
    done = wait_run(client, auth_header, bot_id, nxt.json()["run_id"])
    assert done["run"]["status"] == "completed"
    assert app.state.runtime.bridge_recycles == 0


def test_dead_wait_retries_same_send(client, auth_header) -> None:
    from artek_buddy.main import app
    from artek_buddy.runtime.cursor_wait import DEAD_WAIT_NEXT_STEP

    bot_id = create_bot(client, auth_header, "WaitDead")["id"]
    first = client.post(
        f"/v1/threads/{bot_id}/messages",
        headers=auth_header,
        json={"text": "hello"},
    )
    assert first.status_code == 200
    done = wait_run(client, auth_header, bot_id, first.json()["run_id"])
    assert done["run"]["status"] == "completed"
    assert app.state.runtime.bridge_recycles == 0
    dead = client.post(
        f"/v1/threads/{bot_id}/messages",
        headers=auth_header,
        json={"text": "please e2e-dead-wait"},
    )
    assert dead.status_code == 200
    snap = wait_run(client, auth_header, bot_id, dead.json()["run_id"])
    assert snap["run"]["status"] == "completed"
    assert not snap["run"].get("error")
    assert DEAD_WAIT_NEXT_STEP not in (snap["run"].get("error") or "")
    assert "Send again" not in "\n".join(message_texts(snap))
    assert "ok" in message_texts(snap)
    assert app.state.runtime.bridge_recycles == 1


def test_dead_wait_stuck_still_fails_once(client, auth_header) -> None:
    from artek_buddy.main import app
    from artek_buddy.runtime.cursor_wait import DEAD_WAIT_NEXT_STEP

    bot_id = create_bot(client, auth_header, "WaitStuck")["id"]
    first = client.post(
        f"/v1/threads/{bot_id}/messages",
        headers=auth_header,
        json={"text": "hello"},
    )
    assert first.status_code == 200
    wait_run(client, auth_header, bot_id, first.json()["run_id"])
    stuck = client.post(
        f"/v1/threads/{bot_id}/messages",
        headers=auth_header,
        json={"text": "please e2e-dead-wait-stuck"},
    )
    assert stuck.status_code == 200
    snap = wait_run(client, auth_header, bot_id, stuck.json()["run_id"])
    assert snap["run"]["status"] == "failed"
    assert snap["run"].get("error") == DEAD_WAIT_NEXT_STEP
    assert "Send again" in (snap["run"].get("error") or "")
    assert app.state.runtime.bridge_recycles == 1
    nxt = client.post(
        f"/v1/threads/{bot_id}/messages",
        headers=auth_header,
        json={"text": "hello"},
    )
    assert nxt.status_code == 200
    recovered = wait_run(client, auth_header, bot_id, nxt.json()["run_id"])
    assert recovered["run"]["status"] == "completed"
    assert "ok" in message_texts(recovered)


def test_completed_run_does_not_recycle_the_bridge(client, auth_header) -> None:
    from artek_buddy.main import app

    bot_id = create_bot(client, auth_header, "AuthOk")["id"]
    sent = client.post(
        f"/v1/threads/{bot_id}/messages",
        headers=auth_header,
        json={"text": "hello"},
    )
    assert sent.status_code == 200
    snap = wait_run(client, auth_header, bot_id, sent.json()["run_id"])
    assert snap["run"]["status"] == "completed"
    assert not snap["run"].get("error")
    assert app.state.runtime.bridge_recycles == 0
