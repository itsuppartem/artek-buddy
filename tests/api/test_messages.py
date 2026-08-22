from __future__ import annotations

from tests.api.helpers import create_bot, message_texts, wait_run

from artek_buddy.runtime.scripted import E2E_OLDER_PREFIX


def test_thread_messages_page_and_older_cursor(client, auth_header) -> None:
    bot_id = create_bot(client, auth_header, "Pager")["id"]
    sent = client.post(
        f"/v1/threads/{bot_id}/messages",
        headers=auth_header,
        json={"text": "please e2e-load-earlier"},
    )
    assert sent.status_code == 200
    snap = wait_run(client, auth_header, bot_id, sent.json()["run_id"])
    assert snap["run"]["status"] == "completed"
    assert snap.get("older_cursor") is not None

    page = client.get(
        f"/v1/threads/{bot_id}/messages",
        headers=auth_header,
        params={"limit": 50},
    )
    assert page.status_code == 200
    body = page.json()
    assert body["thread_id"] == snap["thread_id"]
    assert len(body["messages"]) == 50
    cursor = body["older_cursor"]
    assert isinstance(cursor, int)

    listed = client.get("/v1/messages", headers=auth_header, params={"bot_id": bot_id, "limit": 50})
    assert listed.status_code == 200
    assert listed.json()["older_cursor"] == cursor
    assert [msg["id"] for msg in listed.json()["messages"]] == [
        msg["id"] for msg in body["messages"]
    ]

    older = client.get(
        f"/v1/threads/{bot_id}/messages",
        headers=auth_header,
        params={"before": cursor, "limit": 50},
    )
    assert older.status_code == 200
    older_body = older.json()
    assert older_body["older_cursor"] is None
    assert f"{E2E_OLDER_PREFIX}00" in message_texts(older_body)


def test_list_messages_missing_bot_is_404(client, auth_header) -> None:
    response = client.get("/v1/messages", headers=auth_header, params={"bot_id": "bot_missing"})
    assert response.status_code == 404


def test_thread_messages_missing_bot_is_404(client, auth_header) -> None:
    response = client.get("/v1/threads/bot_missing/messages", headers=auth_header)
    assert response.status_code == 404
