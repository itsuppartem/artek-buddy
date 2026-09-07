from __future__ import annotations

from tests.api.helpers import create_bot, wait_run

from artek_buddy.bus import HEARTBEAT, EventHub


async def _workspace_one_frame(self, heartbeat_s: float = 15.0):
    yield HEARTBEAT


async def _thread_live_only(
    self,
    bot_id: str,
    after: str | None = None,
    heartbeat_s: float = 15.0,
    replay: bool = True,
):
    yield HEARTBEAT


def _message_activity(store, bot_id: str) -> list:
    records, _gap = store.replay_activity(resource=bot_id)
    return [row for row in records if row.event_type == "message.created"]


def test_message_write_inserts_activity_in_same_transaction(client, auth_header) -> None:
    store = client.app.state.store
    bot = create_bot(client, auth_header, "ActivityTx")
    sent = client.post(
        f"/v1/threads/{bot['id']}/messages",
        headers=auth_header,
        json={"text": "hello activity"},
    )
    assert sent.status_code == 200
    wait_run(client, auth_header, bot["id"], sent.json()["run_id"])

    records = _message_activity(store, bot["id"])
    assert records
    roles = {row.payload.get("role") for row in records}
    assert "user" in roles
    for row in records:
        assert "token" not in row.payload
        assert "tool_args" not in row.payload
        assert "screenshot" not in row.payload
        assert "hello activity" not in str(row.payload)


def test_activity_replay_survives_cleared_event_hub(client, auth_header, monkeypatch) -> None:
    bot = create_bot(client, auth_header, "ActivityReplay")
    sent = client.post(
        f"/v1/threads/{bot['id']}/messages",
        headers=auth_header,
        json={"text": "persist me"},
    )
    assert sent.status_code == 200
    wait_run(client, auth_header, bot["id"], sent.json()["run_id"])

    client.app.state.hub._buf.clear()
    monkeypatch.setattr(EventHub, "subscribe", _thread_live_only)
    response = client.get(
        f"/v1/threads/{bot['id']}/events",
        headers={**auth_header, "Last-Event-ID": "0"},
    )
    assert response.status_code == 200
    assert "text/event-stream" in response.headers.get("content-type", "")
    assert "thread.message.created" in response.text
    assert "persist me" in response.text


def test_thread_events_emit_gap_when_store_reports_gap(
    client, auth_header, monkeypatch
) -> None:
    bot = create_bot(client, auth_header, "ActivityGapSse")
    monkeypatch.setattr(
        type(client.app.state.store),
        "replay_activity",
        lambda self, **kwargs: ([], True),
    )
    monkeypatch.setattr(EventHub, "subscribe", _thread_live_only)
    response = client.get(
        f"/v1/threads/{bot['id']}/events?after_sequence=3",
        headers=auth_header,
    )
    assert response.status_code == 200
    assert "thread.replay.gap" in response.text
    assert "resync" in response.text


def test_activity_secrets_never_persist(client) -> None:
    store = client.app.state.store
    record = store.append_activity(
        "message.created",
        actor="user",
        resource="bot_secret",
        payload={
            "id": "msg_secret",
            "token": "crsr_should_not_store",
            "tool_args": {"cmd": "echo secret"},
            "screenshot": "iVBORw0KGgo=",
            "note": "safe",
        },
    )
    assert "token" not in record.payload
    assert "tool_args" not in record.payload
    assert "screenshot" not in record.payload
    assert record.payload["note"] == "safe"
    replayed, gap = store.replay_activity(after_seq=record.seq - 1, resource="bot_secret")
    assert gap is False
    assert replayed
    assert "token" not in replayed[0].payload


def test_suspended_member_gets_no_activity_replay(client, host_token, monkeypatch) -> None:
    store = client.app.state.store
    code = client.post(
        "/v1/devices/pairing",
        headers={"Authorization": f"Bearer {host_token}"},
    ).json()["code"]
    device = client.post(
        "/v1/devices",
        json={"name": "ActivityPhone", "platform": "web", "pairing_code": code},
    ).json()
    auth = {"Authorization": f"Bearer {device['token']}"}
    bot = create_bot(client, auth, "ActivityRevoke")
    sent = client.post(
        f"/v1/threads/{bot['id']}/messages",
        headers=auth,
        json={"text": "before suspend"},
    )
    assert sent.status_code == 200
    wait_run(client, auth, bot["id"], sent.json()["run_id"])

    store.suspend_member("mem_owner")
    monkeypatch.setattr(EventHub, "subscribe", _thread_live_only)
    monkeypatch.setattr(EventHub, "subscribe_workspace", _workspace_one_frame)
    try:
        thread = client.get(
            f"/v1/threads/{bot['id']}/events?after_sequence=0",
            headers=auth,
        )
        workspace = client.get("/v1/events?after_sequence=0", headers=auth)
        assert thread.status_code == 403
        assert workspace.status_code == 403
    finally:
        store.activate_member("mem_owner")
