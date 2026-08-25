from __future__ import annotations

from tests.api.helpers import create_bot, wait_run


def test_ordinary_chat_grows_memory_book_without_panel(client, auth_header) -> None:
    bot_id = create_bot(client, auth_header, "BookChat")["id"]
    sent = client.post(
        f"/v1/threads/{bot_id}/messages",
        headers=auth_header,
        json={"text": "My name is Artek. I live in Belgrade. Never open Gmail."},
    )
    assert sent.status_code == 200
    snap = wait_run(client, auth_header, bot_id, sent.json()["run_id"])
    assert snap["run"]["status"] == "completed"
    listed = client.get(f"/v1/memory?bot_id={bot_id}", headers=auth_header)
    assert listed.status_code == 200
    documents = listed.json()["documents"]
    blob = "\n".join(str(item.get("content") or "") for item in documents)
    assert "Artek" in blob
    assert "Belgrade" in blob
    assert "Gmail" in blob
    identity = [item for item in documents if "Artek" in str(item.get("content") or "")]
    assert identity
    assert any("Belgrade" in str(item.get("content") or "") for item in identity)


def test_ordinary_chat_rewrites_identity_when_the_city_changes(client, auth_header) -> None:
    bot_id = create_bot(client, auth_header, "BookRewrite")["id"]
    first = client.post(
        f"/v1/threads/{bot_id}/messages",
        headers=auth_header,
        json={"text": "My name is Artek. I live in Belgrade."},
    )
    assert first.status_code == 200
    assert wait_run(client, auth_header, bot_id, first.json()["run_id"])["run"]["status"] == (
        "completed"
    )
    later = client.post(
        f"/v1/threads/{bot_id}/messages",
        headers=auth_header,
        json={"text": "I live in Subotica."},
    )
    assert later.status_code == 200
    assert wait_run(client, auth_header, bot_id, later.json()["run_id"])["run"]["status"] == (
        "completed"
    )
    listed = client.get(f"/v1/memory?bot_id={bot_id}", headers=auth_header)
    assert listed.status_code == 200
    identity = [
        item
        for item in listed.json()["documents"]
        if "Artek" in str(item.get("content") or "")
        or "Subotica" in str(item.get("content") or "")
        or "Belgrade" in str(item.get("content") or "")
    ]
    blob = "\n".join(str(item.get("content") or "") for item in identity)
    assert "Artek" in blob
    assert "Subotica" in blob
    assert "Belgrade" not in blob


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
    assert bad.status_code == 400

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
    assert bad.status_code == 400

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


def test_routine_test_run_completes(client, auth_header) -> None:
    bot_id = create_bot(client, auth_header, "RoutineFire")["id"]
    created = client.post(
        "/v1/routines",
        headers=auth_header,
        json={
            "bot_id": bot_id,
            "name": "Ping",
            "prompt": "hello",
            "cron": "0 9 * * *",
            "timezone": "UTC",
            "active": True,
        },
    )
    assert created.status_code == 200
    fired = client.post(f"/v1/routines/{created.json()['id']}/test", headers=auth_header)
    assert fired.status_code == 200
    run_id = fired.json()["run_id"]
    snap = wait_run(client, auth_header, bot_id, run_id)
    assert snap["run"]["status"] == "completed"


def test_artifacts_empty_and_missing(client, auth_header) -> None:
    bot_id = create_bot(client, auth_header, "Arts")["id"]
    listed = client.get("/v1/artifacts", headers=auth_header, params={"bot_id": bot_id})
    assert listed.status_code == 200
    assert listed.json()["artifacts"] == []
    missing = client.get("/v1/artifacts/art_missing", headers=auth_header)
    assert missing.status_code == 404
    no_bot = client.get("/v1/artifacts", headers=auth_header)
    assert no_bot.status_code == 422


def test_subagents_empty_and_missing_stop(client, auth_header) -> None:
    bot_id = create_bot(client, auth_header, "Subs")["id"]
    listed = client.get(f"/v1/bots/{bot_id}/subagents", headers=auth_header)
    assert listed.status_code == 200
    assert listed.json()["subagents"] == []
    stopped = client.post(f"/v1/bots/{bot_id}/subagents/sub_missing/stop", headers=auth_header)
    assert stopped.status_code == 404
    restarted = client.post(f"/v1/bots/{bot_id}/subagents/sub_missing/restart", headers=auth_header)
    assert restarted.status_code == 404
    steered = client.post(
        f"/v1/bots/{bot_id}/subagents/sub_missing/steer",
        headers=auth_header,
        json={"text": "keep going"},
    )
    assert steered.status_code == 404
