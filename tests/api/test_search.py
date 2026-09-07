from __future__ import annotations

import secrets

from tests.api.helpers import create_bot, wait_run


def _guest_headers(store) -> tuple[dict[str, str], str]:
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
    device = store.create_device("GuestSearch", platform="web", member_id=member_id)
    return {"Authorization": f"Bearer {device.token}"}, member_id


def test_search_requires_principal(client) -> None:
    missing = client.get("/v1/search", params={"q": "hello"})
    assert missing.status_code == 401
    bad = client.get("/v1/search", params={"q": "hello"}, headers={"Authorization": "Bearer nope"})
    assert bad.status_code == 403


def test_owner_search_finds_message_memory_artifact_and_bot_name(client, auth_header) -> None:
    token = secrets.token_hex(6)
    bot = create_bot(client, auth_header, f"Desk {token}", title="shipping role")
    bot_id = bot["id"]
    sent = client.post(
        f"/v1/threads/{bot_id}/messages",
        headers=auth_header,
        json={"text": f"visiblefts {token} in chat"},
    )
    assert sent.status_code == 200
    wait_run(client, auth_header, bot_id, sent.json()["run_id"])

    mem = client.post(
        "/v1/memory",
        headers=auth_header,
        json={
            "scope": "user",
            "path": f"entries/owner/note-{token}.md",
            "content": f"memfts {token} stays visible",
        },
    )
    assert mem.status_code == 200, mem.text

    store = client.app.state.store
    store.save_artifact(
        bot_id=bot_id,
        name=f"export {token}.txt",
        mime_type="text/plain",
        size=4,
        storage_path=f"/tmp/export-{token}",
    )

    hits = client.get("/v1/search", headers=auth_header, params={"q": f"visiblefts {token}"})
    assert hits.status_code == 200
    body = hits.json()
    assert "total" not in body
    assert body["has_more"] is False
    kinds = {item["document_kind"] for item in body["hits"]}
    resources = {item["resource_id"] for item in body["hits"]}
    assert "message" in kinds
    assert bot_id in resources

    memory_hits = client.get("/v1/search", headers=auth_header, params={"q": f"memfts {token}"})
    assert any(item["document_kind"] == "memory" for item in memory_hits.json()["hits"]), memory_hits.json()

    file_hits = client.get("/v1/search", headers=auth_header, params={"q": f"export {token}"})
    assert any(item["document_kind"] == "artifact" for item in file_hits.json()["hits"])

    name_hits = client.get("/v1/search", headers=auth_header, params={"q": f"Desk {token}"})
    assert any(item["document_kind"] == "bot" for item in name_hits.json()["hits"])


def test_search_skips_tool_payloads_and_escapes_snippets(client, auth_header) -> None:
    token = secrets.token_hex(6)
    bot = create_bot(client, auth_header, f"Leak {token}")
    store = client.app.state.store
    bot_row = store.get_bot(bot["id"])
    assert bot_row is not None
    store.append_bot_message(
        bot_row,
        [
            {"kind": "plugin", "name": "mail", "text": f"PLUGINSECRET {token}"},
            {"kind": "progress", "text": f"PROGRESSSECRET {token}"},
            {"kind": "text", "text": f"<img src=x onerror=alert(1)> xss {token}"},
        ],
    )
    hidden = client.get("/v1/search", headers=auth_header, params={"q": f"PLUGINSECRET {token}"})
    assert hidden.status_code == 200
    assert hidden.json()["hits"] == []
    progress = client.get(
        "/v1/search", headers=auth_header, params={"q": f"PROGRESSSECRET {token}"}
    )
    assert progress.json()["hits"] == []
    xss = client.get("/v1/search", headers=auth_header, params={"q": f"xss {token}"})
    assert xss.status_code == 200
    assert xss.json()["hits"]
    snippet = xss.json()["hits"][0]["snippet"]
    assert "<img" not in snippet
    assert "&lt;" in snippet or "xss" in snippet


def test_guest_and_hidden_high_rank_cannot_leak_via_pagination(client, auth_header) -> None:
    token = secrets.token_hex(6)
    bot = create_bot(client, auth_header, f"Visible {token}")
    bot_id = bot["id"]
    sent = client.post(
        f"/v1/threads/{bot_id}/messages",
        headers=auth_header,
        json={"text": f"needle-{token}"},
    )
    assert sent.status_code == 200
    wait_run(client, auth_header, bot_id, sent.json()["run_id"])

    store = client.app.state.store
    hidden_id = f"bot_hidden_{token}"
    for index in range(5):
        store.upsert_search_document(
            document_kind="message",
            resource_id=hidden_id,
            source_id=f"msg_hidden_{token}_{index}",
            title="hidden",
            body=f"needle-{token} " * 12,
        )

    owner = client.get(
        "/v1/search",
        headers=auth_header,
        params={"q": f"needle-{token}", "limit": 1},
    )
    assert owner.status_code == 200
    page = owner.json()
    assert page["hits"]
    assert page["hits"][0]["resource_id"] == bot_id
    assert hidden_id not in {item["resource_id"] for item in page["hits"]}
    assert "total" not in page

    guest_headers, member_id = _guest_headers(store)
    guest = client.get(
        "/v1/search",
        headers=guest_headers,
        params={"q": f"needle-{token}", "limit": 1},
    )
    assert guest.status_code == 200
    assert guest.json()["hits"] == []
    assert guest.json()["has_more"] is False
    assert "total" not in guest.json()
    empty = client.get("/v1/search", headers=guest_headers, params={"q": "zzzz-no-such"})
    assert empty.json()["hits"] == []

    store.suspend_member(member_id)
    revoked = client.get("/v1/search", headers=guest_headers, params={"q": f"needle-{token}"})
    assert revoked.status_code == 403


def test_delete_bot_and_memory_drop_hits(client, auth_header) -> None:
    token = secrets.token_hex(6)
    bot = create_bot(client, auth_header, f"Gone {token}")
    bot_id = bot["id"]
    sent = client.post(
        f"/v1/threads/{bot_id}/messages",
        headers=auth_header,
        json={"text": f"tombstone-{token}"},
    )
    assert sent.status_code == 200
    wait_run(client, auth_header, bot_id, sent.json()["run_id"])
    mem = client.post(
        "/v1/memory",
        headers=auth_header,
        json={
            "scope": "user",
            "path": f"entries/owner/gone-{token}.md",
            "content": f"forget-me-{token}",
        },
    )
    assert mem.status_code == 200
    doc_id = mem.json()["id"]
    forgotten = client.delete(f"/v1/memory/{doc_id}", headers=auth_header)
    assert forgotten.status_code == 200
    after_mem = client.get("/v1/search", headers=auth_header, params={"q": f"forget-me-{token}"})
    assert after_mem.json()["hits"] == []

    deleted = client.delete(f"/v1/bots/{bot_id}", headers=auth_header)
    assert deleted.status_code == 200
    after_bot = client.get("/v1/search", headers=auth_header, params={"q": f"tombstone-{token}"})
    assert after_bot.json()["hits"] == []


def test_search_rebuild_is_resumable(client, auth_header) -> None:
    token = secrets.token_hex(6)
    bot = create_bot(client, auth_header, f"Rebuild {token}")
    store = client.app.state.store
    with store._conn() as conn:
        conn.execute("DELETE FROM search_documents WHERE resource_id = %s", (bot["id"],))
        conn.commit()
    missing = client.get("/v1/search", headers=auth_header, params={"q": f"Rebuild {token}"})
    assert missing.json()["hits"] == []

    payload = {"version": 1, "phase": "bots", "after_id": ""}
    first, done = store.rebuild_search_chunk(payload, batch=1)
    assert done is False
    assert first["after_id"] or first["phase"] != "bots"
    second, _ = store.rebuild_search_chunk(first, batch=1)
    assert second["phase"] != first["phase"] or second["after_id"] != first["after_id"]

    store.upsert_search_document(
        document_kind="bot",
        resource_id=bot["id"],
        source_id=bot["id"],
        title=bot["name"],
        body=bot.get("title") or "",
    )
    restored = client.get("/v1/search", headers=auth_header, params={"q": f"Rebuild {token}"})
    assert any(item["resource_id"] == bot["id"] for item in restored.json()["hits"])
