from __future__ import annotations

from artek_buddy.bus import HEARTBEAT, REPLAY_GAP, EventHub
from tests.api.helpers import create_bot, wait_run


async def _workspace_one_frame(self, heartbeat_s: float = 15.0):
    yield HEARTBEAT


async def _thread_replay_then_stop(self, bot_id: str, after: str | None = None, heartbeat_s: float = 15.0):
    yield HEARTBEAT
    if after and not self.has_event(bot_id, after):
        yield REPLAY_GAP
        return
    for event in self.replay(bot_id, after=after):
        yield event


def test_workspace_events_is_sse_and_does_not_hang(client, auth_header, monkeypatch) -> None:
    monkeypatch.setattr(EventHub, "subscribe_workspace", _workspace_one_frame)
    response = client.get("/v1/events", headers=auth_header)
    assert response.status_code == 200
    assert "text/event-stream" in response.headers.get("content-type", "")
    assert ": keepalive" in response.text


def test_thread_events_replay_message_created(client, auth_header, monkeypatch) -> None:
    monkeypatch.setattr(EventHub, "subscribe", _thread_replay_then_stop)
    bot_id = create_bot(client, auth_header, "SseReplay")["id"]
    sent = client.post(
        f"/v1/threads/{bot_id}/messages",
        headers=auth_header,
        json={"text": "hello"},
    )
    assert sent.status_code == 200
    wait_run(client, auth_header, bot_id, sent.json()["run_id"])
    response = client.get(f"/v1/threads/{bot_id}/events", headers=auth_header)
    assert response.status_code == 200
    assert "text/event-stream" in response.headers.get("content-type", "")
    assert "thread.message.created" in response.text


def test_thread_events_missing_bot_is_404(client, auth_header) -> None:
    response = client.get("/v1/threads/bot_missing/events", headers=auth_header)
    assert response.status_code == 404
