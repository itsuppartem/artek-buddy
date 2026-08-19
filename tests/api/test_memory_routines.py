from __future__ import annotations


def test_memory_create_update_export_delete(client, auth_header) -> None:
    bot = client.post("/v1/bots", headers=auth_header, json={"name": "Mem"})
    bot_id = bot.json()["id"]
    created = client.post(
        "/v1/memory",
        headers=auth_header,
        json={
            "scope": "user",
            "path": "entries/owner/note-ci.md",
            "content": "Prefers short answers",
        },
    )
    assert created.status_code == 200
    doc_id = created.json()["id"]

    listed = client.get(f"/v1/memory?bot_id={bot_id}", headers=auth_header)
    assert listed.status_code == 200
    assert any(item["id"] == doc_id for item in listed.json()["documents"])

    updated = client.patch(
        f"/v1/memory/{doc_id}",
        headers=auth_header,
        json={"content": "Prefers short answers, no emoji"},
    )
    assert updated.status_code == 200

    exported = client.get(f"/v1/memory/export?bot_id={bot_id}", headers=auth_header)
    assert exported.status_code == 200
    assert "Prefers short answers" in exported.json()["markdown"]

    bad = client.post(
        "/v1/memory",
        headers=auth_header,
        json={"scope": "user", "path": "../secret", "content": "nope"},
    )
    assert bad.status_code in {400, 422}

    removed = client.delete(f"/v1/memory/{doc_id}", headers=auth_header)
    assert removed.status_code == 200


def test_routines_valid_and_invalid_cron(client, auth_header) -> None:
    bot = client.post("/v1/bots", headers=auth_header, json={"name": "Cron"})
    bot_id = bot.json()["id"]
    created = client.post(
        "/v1/routines",
        headers=auth_header,
        json={
            "bot_id": bot_id,
            "name": "Morning",
            "prompt": "brief me",
            "cron": "0 9 * * *",
            "timezone": "UTC",
            "active": True,
        },
    )
    assert created.status_code == 200
    routine_id = created.json()["id"]

    bad = client.post(
        "/v1/routines",
        headers=auth_header,
        json={
            "bot_id": bot_id,
            "name": "Bad",
            "prompt": "nope",
            "cron": "not-a-cron",
            "timezone": "UTC",
        },
    )
    assert bad.status_code in {400, 422}

    paused = client.patch(
        f"/v1/routines/{routine_id}",
        headers=auth_header,
        json={"active": False},
    )
    assert paused.status_code == 200
    assert paused.json()["active"] is False

    listed = client.get(f"/v1/routines?bot_id={bot_id}", headers=auth_header)
    assert any(item["id"] == routine_id for item in listed.json()["routines"])

    deleted = client.delete(f"/v1/routines/{routine_id}", headers=auth_header)
    assert deleted.status_code == 200
