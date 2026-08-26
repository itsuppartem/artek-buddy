from __future__ import annotations

import json

import pytest
from tests.api.helpers import consent_id_from_thread, create_bot, wait_run, wait_run_status

from artek_buddy.books import MAX_BOOKS, BookError


def _book_blocks(payload: dict) -> list[dict]:
    return [
        block
        for message in payload.get("messages") or []
        for block in message.get("blocks") or []
        if block.get("kind") == "book"
    ]


def test_books_require_auth_and_missing_bot_is_404(client, auth_header) -> None:
    assert client.get("/v1/bots/bot_missing/books").status_code == 401
    assert (
        client.get(
            "/v1/bots/bot_missing/books",
            headers={"Authorization": "Bearer nope"},
        ).status_code
        == 403
    )
    missing = client.get("/v1/bots/bot_missing/books", headers=auth_header)
    assert missing.status_code == 404
    assert missing.json()["detail"] == "bot not found"


def _allow_install(client, auth_header, bot_id: str, run_id: str) -> dict:
    snap = wait_run_status(client, auth_header, bot_id, run_id, "waiting_input")
    consent_id = consent_id_from_thread(snap)
    allowed = client.post(
        f"/v1/consents/{consent_id}",
        headers=auth_header,
        json={"decision": "once"},
    )
    assert allowed.status_code == 200, allowed.text
    return wait_run(client, auth_header, bot_id, run_id)


def test_install_run_and_forget_playbook_in_the_thread(client, auth_header) -> None:
    bot = create_bot(client, auth_header, "BookChat")
    empty = client.get(f"/v1/bots/{bot['id']}/books", headers=auth_header)
    assert empty.status_code == 200
    assert empty.json()["books"] == []

    saved = client.post(
        f"/v1/threads/{bot['id']}/messages",
        headers=auth_header,
        json={"text": "please e2e-install-book"},
    )
    assert saved.status_code == 200
    after_save = _allow_install(client, auth_header, bot["id"], saved.json()["run_id"])
    books = _book_blocks(after_save)
    assert books
    assert books[0]["name"] == "Invoice"
    assert books[0]["action"] == "saved"
    assert "please run Invoice" in books[0]["text"]

    listed = client.get(f"/v1/bots/{bot['id']}/books", headers=auth_header)
    assert listed.status_code == 200
    rows = listed.json()["books"]
    assert [row["name"] for row in rows] == ["Invoice"]
    assert rows[0]["slug"] == "invoice"
    assert rows[0]["when_to_use"] == "When I say invoice"
    assert "body" not in rows[0] or rows[0]["body"] is None
    assert "Open the invoice site" not in json.dumps(listed.json())

    other = create_bot(client, auth_header, "BookOther")
    other_list = client.get(f"/v1/bots/{other['id']}/books", headers=auth_header)
    assert other_list.json()["books"] == []

    ran = client.post(
        f"/v1/threads/{bot['id']}/messages",
        headers=auth_header,
        json={"text": "please run Invoice"},
    )
    assert ran.status_code == 200
    after_run = wait_run(client, auth_header, bot["id"], ran.json()["run_id"])
    opened = [block for block in _book_blocks(after_run) if block.get("action") == "opened"]
    assert opened
    assert opened[0]["name"] == "Invoice"
    assert "Open the invoice site" in opened[0]["text"]

    forgotten = client.post(
        f"/v1/threads/{bot['id']}/messages",
        headers=auth_header,
        json={"text": "please e2e-forget-book"},
    )
    assert forgotten.status_code == 200
    after_forget = wait_run(client, auth_header, bot["id"], forgotten.json()["run_id"])
    dropped = [block for block in _book_blocks(after_forget) if block.get("action") == "forgotten"]
    assert dropped
    assert dropped[0]["name"] == "Invoice"
    gone = client.get(f"/v1/bots/{bot['id']}/books", headers=auth_header)
    assert gone.json()["books"] == []


def test_deny_does_not_store_an_installed_book(client, auth_header) -> None:
    bot = create_bot(client, auth_header, "BookDeny")
    sent = client.post(
        f"/v1/threads/{bot['id']}/messages",
        headers=auth_header,
        json={"text": "please e2e-install-book"},
    )
    assert sent.status_code == 200
    run_id = sent.json()["run_id"]
    snap = wait_run_status(client, auth_header, bot["id"], run_id, "waiting_input")
    consent_id = consent_id_from_thread(snap)
    denied = client.post(
        f"/v1/consents/{consent_id}",
        headers=auth_header,
        json={"decision": "deny"},
    )
    assert denied.status_code == 200
    wait_run(client, auth_header, bot["id"], run_id)
    listed = client.get(f"/v1/bots/{bot['id']}/books", headers=auth_header)
    assert listed.json()["books"] == []
    assert not [
        block
        for block in _book_blocks(
            client.get(f"/v1/threads/{bot['id']}", headers=auth_header).json()
        )
        if block.get("action") == "saved"
    ]


def test_save_book_rejects_empty_and_caps_this_chat(client, auth_header) -> None:
    bot = create_bot(client, auth_header, "BookCap")
    store = client.app.state.store
    with pytest.raises(BookError, match="name cannot be empty"):
        store.save_skill_book(bot["id"], "   ", "when", "body")

    for index in range(MAX_BOOKS):
        store.save_skill_book(
            bot["id"],
            f"Play {index}",
            f"When play {index}",
            f"Do step {index}",
        )
    listed = client.get(f"/v1/bots/{bot['id']}/books", headers=auth_header)
    assert len(listed.json()["books"]) == MAX_BOOKS
    with pytest.raises(BookError, match="20 books"):
        store.save_skill_book(bot["id"], "Extra", "when extra", "body extra")
    same = store.save_skill_book(bot["id"], "Play 0", "When play 0 revised", "Do step 0 again")
    assert same.name == "Play 0"
    assert same.body == "Do step 0 again"
    assert (
        len(client.get(f"/v1/bots/{bot['id']}/books", headers=auth_header).json()["books"])
        == MAX_BOOKS
    )
