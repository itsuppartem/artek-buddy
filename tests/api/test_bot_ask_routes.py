from __future__ import annotations

from tests.api.helpers import create_bot, message_texts, wait_run, wait_thread_has


def _block_kinds(payload: dict) -> list[str]:
    kinds: list[str] = []
    for msg in payload.get("messages") or []:
        for block in msg.get("blocks") or []:
            kind = block.get("kind")
            if kind:
                kinds.append(str(kind))
    return kinds


def test_chat_ask_other_bot_returns_last_text_without_copying_work(client, auth_header) -> None:
    asker = create_bot(client, auth_header, "AskPeer", computer_mode="dedicated")
    knows = create_bot(client, auth_header, "KnowsPeer", computer_mode="dedicated")
    before_a = client.get(f"/v1/threads/{asker['id']}", headers=auth_header).json()
    before_b = client.get(f"/v1/threads/{knows['id']}", headers=auth_header).json()
    assert before_a["computer"]["bot_id"] == asker["id"]
    assert before_b["computer"]["bot_id"] == knows["id"]
    sent = client.post(
        f"/v1/threads/{asker['id']}/messages",
        headers=auth_header,
        json={"text": f"please e2e-ask-bot {knows['name']} | what city do you know"},
    )
    assert sent.status_code == 200
    asked = wait_thread_has(client, auth_header, asker["id"], f"Asked {knows['name']}")
    assert any(
        block.get("kind") == "child_bot" and block.get("name") == knows["name"]
        for msg in asked.get("messages") or []
        for block in msg.get("blocks") or []
    )
    inbound = wait_thread_has(client, auth_header, knows["id"], "what city do you know")
    assert any("AskPeer" in text for text in message_texts(inbound))
    wait_thread_has(client, auth_header, knows["id"], "ready to answer")
    answered = wait_thread_has(client, auth_header, asker["id"], "Subotica")
    assert "Opened Chromium" not in "\n".join(message_texts(answered))
    assert "computer" not in _block_kinds(answered)
    after_b = client.get(f"/v1/threads/{knows['id']}", headers=auth_header).json()
    after_a = client.get(f"/v1/threads/{asker['id']}", headers=auth_header).json()
    assert after_b["computer"]["bot_id"] == knows["id"]
    assert after_a["computer"]["bot_id"] == asker["id"]
    assert after_b["computer"]["mode"] == "dedicated"
    assert "please e2e-ask-bot" not in "\n".join(message_texts(after_b))


def test_ask_api_rejects_empty_self_missing_archived_deleted(client, auth_header) -> None:
    asker = create_bot(client, auth_header, "AskGate")
    other = create_bot(client, auth_header, "KnowsGate")
    empty = client.post(
        f"/v1/bots/{asker['id']}/asks",
        headers=auth_header,
        json={"bot": other["name"], "text": "  "},
    )
    assert empty.status_code == 400
    self_name = client.post(
        f"/v1/bots/{asker['id']}/asks",
        headers=auth_header,
        json={"bot": asker["name"], "text": "hi"},
    )
    assert self_name.status_code == 400
    missing = client.post(
        f"/v1/bots/{asker['id']}/asks",
        headers=auth_header,
        json={"bot": "no-such-bot", "text": "hi"},
    )
    assert missing.status_code == 404
    client.post(f"/v1/bots/{other['id']}/archive", headers=auth_header)
    archived = client.post(
        f"/v1/bots/{asker['id']}/asks",
        headers=auth_header,
        json={"bot": other["id"], "text": "hi"},
    )
    assert archived.status_code == 404
    gone = create_bot(client, auth_header, "AskGone")
    client.delete(f"/v1/bots/{gone['id']}", headers=auth_header)
    deleted = client.post(
        f"/v1/bots/{asker['id']}/asks",
        headers=auth_header,
        json={"bot": gone["id"], "text": "hi"},
    )
    assert deleted.status_code == 404


def test_ask_api_starts_dest_and_returns_compact_reply(client, auth_header) -> None:
    asker = create_bot(client, auth_header, "AskHttp", computer_mode="dedicated")
    knows = create_bot(client, auth_header, "KnowsHttp", computer_mode="dedicated")
    asked = client.post(
        f"/v1/bots/{asker['id']}/asks",
        headers=auth_header,
        json={"bot": knows["name"], "text": "what city do you know"},
    )
    assert asked.status_code == 200
    body = asked.json()
    assert body["ok"] is True
    assert body["to_bot_id"] == knows["id"]
    assert body["name"] == knows["name"]
    assert body["to_run_id"]
    wait_run(client, auth_header, knows["id"], body["to_run_id"])
    wait_thread_has(client, auth_header, knows["id"], "AskHttp asked")
    wait_thread_has(client, auth_header, asker["id"], f"Asked {knows['name']}")
    answered = wait_thread_has(client, auth_header, asker["id"], "Subotica")
    assert "computer" not in _block_kinds(answered)
    snap_b = client.get(f"/v1/threads/{knows['id']}", headers=auth_header).json()
    assert snap_b["computer"]["bot_id"] == knows["id"]
