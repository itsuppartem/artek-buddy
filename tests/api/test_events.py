from __future__ import annotations

from tests.api.helpers import create_bot, wait_run


def test_workspace_events_is_sse_and_does_not_hang(client, auth_header) -> None:
    with client.stream("GET", "/v1/events", headers=auth_header, timeout=5.0) as response:
        assert response.status_code == 200
        assert "text/event-stream" in response.headers.get("content-type", "")


def test_thread_events_replay_message_created(client, auth_header) -> None:
    bot_id = create_bot(client, auth_header, "SseReplay")["id"]
    sent = client.post(
        f"/v1/threads/{bot_id}/messages",
        headers=auth_header,
        json={"text": "hello"},
    )
    assert sent.status_code == 200
    wait_run(client, auth_header, bot_id, sent.json()["run_id"])
    with client.stream("GET", f"/v1/threads/{bot_id}/events", headers=auth_header, timeout=8.0) as response:
        assert response.status_code == 200
        assert "text/event-stream" in response.headers.get("content-type", "")
        buf = ""
        for chunk in response.iter_text():
            buf += chunk
            if "thread.message.created" in buf:
                break
        else:
            raise AssertionError("replay did not include thread.message.created")


def test_thread_events_missing_bot_is_404(client, auth_header) -> None:
    response = client.get("/v1/threads/bot_missing/events", headers=auth_header)
    assert response.status_code == 404
