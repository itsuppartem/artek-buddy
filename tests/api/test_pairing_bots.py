from __future__ import annotations

from tests.support import mask_secret


def test_pairing_happy_and_reuse_fails(client, auth_header) -> None:
    minted = client.post("/v1/devices/pairing", headers=auth_header)
    assert minted.status_code == 200
    code = minted.json()["code"]
    mask_secret(code)
    created = client.post(
        "/v1/devices",
        json={"name": "CI laptop", "platform": "linux", "pairing_code": code},
    )
    assert created.status_code == 200
    token = created.json()["token"]
    mask_secret(token)
    assert token.startswith("dev_")

    reused = client.post(
        "/v1/devices",
        json={"name": "CI laptop 2", "platform": "linux", "pairing_code": code},
    )
    assert reused.status_code == 403

    listed = client.get("/v1/devices", headers={"Authorization": f"Bearer {token}"})
    assert listed.status_code == 200
    assert len(listed.json()["devices"]) >= 1


def test_pairing_bad_code(client) -> None:
    response = client.post(
        "/v1/devices",
        json={"name": "nope", "platform": "linux", "pairing_code": "ZZZZ-ZZZZ"},
    )
    assert response.status_code == 403


def test_bot_crud_archive_restore_delete(client, auth_header) -> None:
    created = client.post(
        "/v1/bots",
        headers=auth_header,
        json={"name": "Research", "title": "notes", "computer_mode": "team"},
    )
    assert created.status_code == 200
    bot_id = created.json()["id"]

    listed = client.get("/v1/bots", headers=auth_header)
    assert any(bot["id"] == bot_id for bot in listed.json()["bots"])

    patched = client.patch(
        f"/v1/bots/{bot_id}",
        headers=auth_header,
        json={"name": "Research 2", "computer_mode": "dedicated"},
    )
    assert patched.status_code == 200
    assert patched.json()["name"] == "Research 2"
    assert patched.json()["computer_mode"] == "dedicated"

    archived = client.post(f"/v1/bots/{bot_id}/archive", headers=auth_header)
    assert archived.status_code == 200
    inbox = client.get("/v1/bots", headers=auth_header)
    assert all(bot["id"] != bot_id for bot in inbox.json()["bots"])
    hidden = client.get("/v1/bots/archived", headers=auth_header)
    assert any(bot["id"] == bot_id for bot in hidden.json()["bots"])

    restored = client.post(f"/v1/bots/{bot_id}/restore", headers=auth_header)
    assert restored.status_code == 200

    removed = client.delete(f"/v1/bots/{bot_id}", headers=auth_header)
    assert removed.status_code == 200
    gone = client.get(f"/v1/bots/{bot_id}", headers=auth_header)
    assert gone.status_code == 404
