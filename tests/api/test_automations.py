from __future__ import annotations

import secrets
from datetime import UTC, datetime, timedelta

from tests.api.helpers import create_bot, message_texts


def _guest_headers(store) -> dict[str, str]:
    member_id = f"mem_g_{secrets.token_hex(4)}"
    with store._conn() as conn:
        conn.execute(
            """
            INSERT INTO members (id, name, role, state, created_at, updated_at)
            VALUES (%s, 'Guest', 'member', 'active', now(), now())
            """,
            (member_id,),
        )
        conn.commit()
    device = store.create_device("GuestAuto", platform="web", member_id=member_id)
    return {"Authorization": f"Bearer {device.token}"}


def _make_routine(client, auth_header, bot_id: str, **extra) -> dict:
    body = {
        "bot_id": bot_id,
        "name": "Ping",
        "prompt": extra.pop("prompt", "hello from routine"),
        "cron": "0 9 * * *",
        "timezone": "UTC",
        "active": True,
        **extra,
    }
    created = client.post("/v1/routines", headers=auth_header, json=body)
    assert created.status_code == 200, created.text
    return created.json()


def test_guest_cannot_edit_routines(client, auth_header) -> None:
    bot_id = create_bot(client, auth_header, "GuestRtn")["id"]
    guest = _guest_headers(client.app.state.store)
    denied = client.post(
        "/v1/routines",
        headers=guest,
        json={
            "bot_id": bot_id,
            "name": "Nope",
            "prompt": "nope",
            "cron": "0 9 * * *",
        },
    )
    assert denied.status_code == 403


def test_duplicate_manual_trigger_reuses_one_run(client, auth_header) -> None:
    bot_id = create_bot(client, auth_header, "DupRtn")["id"]
    routine = _make_routine(client, auth_header, bot_id)
    event_id = f"click-{secrets.token_hex(4)}"
    first = client.post(
        f"/v1/routines/{routine['id']}/run",
        headers=auth_header,
        json={"trigger_event_id": event_id},
    )
    second = client.post(
        f"/v1/routines/{routine['id']}/run",
        headers=auth_header,
        json={"trigger_event_id": event_id},
    )
    assert first.status_code == 200, first.text
    assert second.status_code == 200, second.text
    assert first.json()["id"] == second.json()["id"]
    listed = client.get(f"/v1/routines/{routine['id']}/runs", headers=auth_header)
    assert listed.status_code == 200
    assert len(listed.json()["runs"]) == 1


def test_edit_during_run_keeps_snapshot_prompt(client, auth_header) -> None:
    token = secrets.token_hex(4)
    bot_id = create_bot(client, auth_header, f"Snap {token}")["id"]
    original = f"alphafts {token}"
    routine = _make_routine(client, auth_header, bot_id, prompt=original)
    event_id = f"snap-{token}"
    fired = client.post(
        f"/v1/routines/{routine['id']}/run",
        headers=auth_header,
        json={"trigger_event_id": event_id},
    )
    assert fired.status_code == 200, fired.text
    patched = client.patch(
        f"/v1/routines/{routine['id']}",
        headers=auth_header,
        json={"prompt": f"betafts {token}"},
    )
    assert patched.status_code == 200
    assert patched.json()["definition_version"] == 2
    listed = client.get(f"/v1/routines/{routine['id']}/runs", headers=auth_header)
    run = listed.json()["runs"][0]
    assert run["snapshot"]["prompt"] == original
    assert run["definition_version"] == 1


def test_approval_gate_pauses_then_fires_on_approve(client, auth_header) -> None:
    token = secrets.token_hex(4)
    bot_id = create_bot(client, auth_header, f"Gate {token}")["id"]
    prompt = f"approvedfts {token}"
    routine = _make_routine(
        client,
        auth_header,
        bot_id,
        prompt=prompt,
        require_approval=True,
    )
    fired = client.post(
        f"/v1/routines/{routine['id']}/run",
        headers=auth_header,
        json={"trigger_event_id": f"gate-{token}"},
    )
    assert fired.status_code == 200, fired.text
    assert fired.json()["state"] == "waiting_for_approval"
    snap = client.get(f"/v1/threads/{bot_id}", headers=auth_header)
    assert snap.status_code == 200
    ask = None
    message_id = None
    run_id = None
    for message in snap.json().get("messages") or []:
        for block in message.get("blocks") or []:
            if block.get("kind") == "ask" and block.get("status") == "pending":
                ask = block
                message_id = message["id"]
                run_id = message["run_id"]
                break
    assert ask is not None
    assert "Approve" in str(ask.get("actions"))
    answered = client.post(
        f"/v1/threads/{bot_id}/answer",
        headers=auth_header,
        json={"run_id": run_id, "message_id": message_id, "answer": "Approve"},
    )
    assert answered.status_code == 200, answered.text
    listed = client.get(f"/v1/routines/{routine['id']}/runs", headers=auth_header)
    assert listed.json()["runs"][0]["state"] in {"queued", "running", "succeeded"}
    with client.app.state.store._conn() as conn:
        jobs = conn.execute(
            """
            SELECT payload FROM jobs
            WHERE job_type = 'routine.fire'
              AND payload->>'automation_run_id' = %s
            """,
            (fired.json()["id"],),
        ).fetchall()
        conn.commit()
    assert jobs
    payload = jobs[0]["payload"]
    if isinstance(payload, str):
        import json

        payload = json.loads(payload)
    assert payload["prompt"] == prompt


def test_approval_deny_does_not_send_prompt(client, auth_header) -> None:
    token = secrets.token_hex(4)
    bot_id = create_bot(client, auth_header, f"Deny {token}")["id"]
    prompt = f"deniedfts {token}"
    routine = _make_routine(
        client,
        auth_header,
        bot_id,
        prompt=prompt,
        require_approval=True,
    )
    fired = client.post(
        f"/v1/routines/{routine['id']}/run",
        headers=auth_header,
        json={"trigger_event_id": f"deny-{token}"},
    )
    assert fired.status_code == 200
    snap = client.get(f"/v1/threads/{bot_id}", headers=auth_header)
    message_id = None
    run_id = None
    for message in snap.json().get("messages") or []:
        for block in message.get("blocks") or []:
            if block.get("kind") == "ask" and block.get("status") == "pending":
                message_id = message["id"]
                run_id = message["run_id"]
    assert message_id and run_id
    denied = client.post(
        f"/v1/threads/{bot_id}/answer",
        headers=auth_header,
        json={"run_id": run_id, "message_id": message_id, "answer": "Deny"},
    )
    assert denied.status_code == 200
    listed = client.get(f"/v1/routines/{routine['id']}/runs", headers=auth_header)
    assert listed.json()["runs"][0]["state"] == "cancelled"
    thread = client.get(f"/v1/threads/{bot_id}", headers=auth_header)
    blob = " ".join(message_texts(thread.json()))
    assert prompt not in blob


def test_approval_wait_does_not_busy_the_team_desk(client, auth_header) -> None:
    waiting = create_bot(client, auth_header, "AskDesk", computer_mode="team")["id"]
    other = create_bot(client, auth_header, "FreeDesk", computer_mode="team")["id"]
    routine = _make_routine(client, auth_header, waiting, require_approval=True)
    fired = client.post(
        f"/v1/routines/{routine['id']}/run",
        headers=auth_header,
        json={"trigger_event_id": "desk-1"},
    )
    assert fired.status_code == 200
    assert fired.json()["state"] == "waiting_for_approval"
    status = client.get(f"/v1/computer/{other}", headers=auth_header)
    assert status.status_code == 200
    assert not status.json().get("busy_bot_name")
    booted = client.post(f"/v1/computer/{other}/boot", headers=auth_header)
    assert booted.status_code == 200


def test_deleted_bot_fails_the_next_automation_step(client, auth_header) -> None:
    bot_id = create_bot(client, auth_header, "GoneRtn")["id"]
    routine = _make_routine(client, auth_header, bot_id, require_approval=True)
    fired = client.post(
        f"/v1/routines/{routine['id']}/run",
        headers=auth_header,
        json={"trigger_event_id": "gone-1"},
    )
    assert fired.status_code == 200
    deleted = client.delete(f"/v1/bots/{bot_id}", headers=auth_header)
    assert deleted.status_code == 200
    again = client.post(
        f"/v1/routines/{routine['id']}/run",
        headers=auth_header,
        json={"trigger_event_id": "gone-2"},
    )
    assert again.status_code == 404


def test_dry_run_does_not_enqueue_a_job(client, auth_header) -> None:
    bot_id = create_bot(client, auth_header, "DryRtn")["id"]
    routine = _make_routine(client, auth_header, bot_id, prompt="dry preview")
    preview = client.post(f"/v1/routines/{routine['id']}/dry-run", headers=auth_header)
    assert preview.status_code == 200
    body = preview.json()
    assert body["dangerous_tools"] is False
    assert body["snapshot"]["prompt"] == "dry preview"
    listed = client.get(f"/v1/routines/{routine['id']}/runs", headers=auth_header)
    assert listed.json()["runs"] == []
    with client.app.state.store._conn() as conn:
        jobs = conn.execute(
            "SELECT id FROM jobs WHERE resource_id = %s AND job_type = 'routine.fire'",
            (routine["id"],),
        ).fetchall()
        conn.commit()
    assert jobs == []


def test_cron_still_enqueues_routine_fire(client, host_token) -> None:
    from artek_buddy.db.shaping import isoformat_utc
    from artek_buddy.worker import host_base, run_once

    store = client.app.state.store
    bot_res = client.post(
        "/v1/bots",
        headers={"Authorization": f"Bearer {host_token}"},
        json={"name": "CronKeep"},
    )
    bot_id = bot_res.json()["id"]
    routine = store.create_routine(
        bot_id=bot_id,
        name="HourlyPing",
        prompt="hello from routine",
        cron="* * * * *",
        active=True,
    )
    past = isoformat_utc(datetime.now(UTC) - timedelta(minutes=1))
    with store._conn() as conn:
        conn.execute("UPDATE routines SET next_run_at = %s WHERE id = %s", (past, routine.id))
        conn.commit()
    run_once(store, host_base(), host_token)
    with store._conn() as conn:
        rows = conn.execute(
            """
            SELECT id, job_type, resource_id, state FROM jobs
            WHERE job_type = 'routine.fire' AND resource_id = %s
            ORDER BY created_at DESC
            """,
            (routine.id,),
        ).fetchall()
        runs = conn.execute(
            """
            SELECT id, trigger_kind FROM automation_runs
            WHERE routine_id = %s
            ORDER BY created_at DESC
            """,
            (routine.id,),
        ).fetchall()
        conn.commit()
    assert len(rows) >= 1
    assert rows[0]["state"] in {"succeeded", "queued", "running"}
    assert runs
    assert runs[0]["trigger_kind"] == "cron"
