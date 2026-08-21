from __future__ import annotations

import base64

from tests.api.helpers import create_bot, message_texts, wait_run


def _note_b64() -> str:
    return base64.b64encode(b"hello from owner").decode("ascii")


def test_upload_attachment_then_send_and_download(client, auth_header) -> None:
    bot_id = create_bot(client, auth_header, "Attach")["id"]
    uploaded = client.post(
        f"/v1/threads/{bot_id}/attachments",
        headers=auth_header,
        json={"files": [{"name": "note.txt", "content_base64": _note_b64(), "mime_type": "text/plain"}]},
    )
    assert uploaded.status_code == 200
    attachments = uploaded.json()["attachments"]
    assert len(attachments) == 1
    art_id = attachments[0]["id"]
    assert art_id.startswith("art_")
    assert attachments[0]["name"] == "note.txt"
    assert attachments[0]["size"] == 16
    assert attachments[0]["mime_type"] == "text/plain"

    listed = client.get("/v1/artifacts", headers=auth_header, params={"bot_id": bot_id})
    assert listed.status_code == 200
    assert any(item["id"] == art_id for item in listed.json()["artifacts"])

    downloaded = client.get(f"/v1/artifacts/{art_id}", headers=auth_header)
    assert downloaded.status_code == 200
    assert downloaded.content == b"hello from owner"

    sent = client.post(
        f"/v1/threads/{bot_id}/messages",
        headers=auth_header,
        json={"text": "see note", "attachment_ids": [art_id]},
    )
    assert sent.status_code == 200
    snap = wait_run(client, auth_header, bot_id, sent.json()["run_id"])
    assert snap["run"]["status"] == "completed"
    assert "see note" in message_texts(snap)


def test_upload_empty_files_is_400(client, auth_header) -> None:
    bot_id = create_bot(client, auth_header, "AttachEmpty")["id"]
    response = client.post(
        f"/v1/threads/{bot_id}/attachments",
        headers=auth_header,
        json={"files": []},
    )
    assert response.status_code == 400


def test_upload_missing_bot_is_404(client, auth_header) -> None:
    response = client.post(
        "/v1/threads/bot_missing/attachments",
        headers=auth_header,
        json={"files": [{"name": "note.txt", "content_base64": _note_b64()}]},
    )
    assert response.status_code == 404


def test_send_inline_attachment_without_text(client, auth_header) -> None:
    bot_id = create_bot(client, auth_header, "AttachInline")["id"]
    sent = client.post(
        f"/v1/threads/{bot_id}/messages",
        headers=auth_header,
        json={"attachments": [{"name": "solo.txt", "content_base64": _note_b64()}]},
    )
    assert sent.status_code == 200
    snap = wait_run(client, auth_header, bot_id, sent.json()["run_id"])
    assert snap["run"]["status"] == "completed"
    file_blocks = [
        block
        for msg in snap["messages"]
        if msg["role"] == "user"
        for block in msg.get("blocks") or []
        if block.get("kind") == "file"
    ]
    assert file_blocks
    assert file_blocks[0]["name"] == "solo.txt"
