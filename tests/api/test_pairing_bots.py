from __future__ import annotations

from tests.api.helpers import create_bot
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


def test_device_token_cannot_mint_pairing(client, auth_header) -> None:
    minted = client.post("/v1/devices/pairing", headers=auth_header)
    code = minted.json()["code"]
    mask_secret(code)
    created = client.post(
        "/v1/devices",
        json={"name": "Paired", "platform": "linux", "pairing_code": code},
    )
    token = created.json()["token"]
    mask_secret(token)
    denied = client.post("/v1/devices/pairing", headers={"Authorization": f"Bearer {token}"})
    assert denied.status_code == 403


def test_device_revoke_self_and_forbid_other(client, auth_header) -> None:
    first_code = client.post("/v1/devices/pairing", headers=auth_header).json()["code"]
    second_code = client.post("/v1/devices/pairing", headers=auth_header).json()["code"]
    mask_secret(first_code)
    mask_secret(second_code)
    first = client.post(
        "/v1/devices",
        json={"name": "AlphaPC", "platform": "linux", "pairing_code": first_code},
    )
    second = client.post(
        "/v1/devices",
        json={"name": "BravoPC", "platform": "linux", "pairing_code": second_code},
    )
    assert first.status_code == 200
    assert second.status_code == 200
    first_id = first.json()["id"]
    second_id = second.json()["id"]
    first_token = first.json()["token"]
    second_token = second.json()["token"]
    mask_secret(first_token)
    mask_secret(second_token)

    stolen = client.delete(
        f"/v1/devices/{first_id}",
        headers={"Authorization": f"Bearer {second_token}"},
    )
    assert stolen.status_code == 403

    revoked = client.delete(
        f"/v1/devices/{first_id}",
        headers={"Authorization": f"Bearer {first_token}"},
    )
    assert revoked.status_code == 200
    assert revoked.json()["revoked_at"]

    dead = client.get("/v1/devices", headers={"Authorization": f"Bearer {first_token}"})
    assert dead.status_code == 403

    missing = client.delete(f"/v1/devices/{first_id}", headers=auth_header)
    assert missing.status_code == 404

    still = client.get("/v1/devices", headers={"Authorization": f"Bearer {second_token}"})
    assert still.status_code == 200
    assert any(row["id"] == second_id for row in still.json()["devices"])


def test_bot_crud_archive_restore_delete(client, auth_header) -> None:
    created = client.post(
        "/v1/bots",
        headers=auth_header,
        json={"name": "Research", "title": "notes", "computer_mode": "team"},
    )
    assert created.status_code == 200
    bot_id = created.json()["id"]
    assert created.json()["computer_mode"] == "team"

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


def test_missing_bot_is_404(client, auth_header) -> None:
    assert client.get("/v1/bots/bot_missing", headers=auth_header).status_code == 404
    assert client.post("/v1/bots/bot_missing/duplicate", headers=auth_header).status_code == 404
    assert client.post("/v1/bots/bot_missing/archive", headers=auth_header).status_code == 404
    assert client.delete("/v1/bots/bot_missing", headers=auth_header).status_code == 404


def test_duplicate_bot_copies_profile(client, auth_header) -> None:
    original = create_bot(client, auth_header, "Research", title="notes", computer_mode="dedicated")
    copied = client.post(f"/v1/bots/{original['id']}/duplicate", headers=auth_header)
    assert copied.status_code == 200
    body = copied.json()
    assert body["id"] != original["id"]
    assert body["name"] == "Research (Copy)"
    assert body["title"] == "notes"
    assert body["computer_mode"] == "dedicated"
    inbox = client.get("/v1/bots", headers=auth_header)
    ids = {bot["id"] for bot in inbox.json()["bots"]}
    assert original["id"] in ids
    assert body["id"] in ids


def test_pin_bot(client, auth_header) -> None:
    bot_id = create_bot(client, auth_header, "Pinned")["id"]
    patched = client.patch(f"/v1/bots/{bot_id}", headers=auth_header, json={"pinned": True})
    assert patched.status_code == 200
    assert patched.json()["pinned"] is True
    got = client.get(f"/v1/bots/{bot_id}", headers=auth_header)
    assert got.json()["pinned"] is True


def test_set_computer_mode_endpoint(client, auth_header) -> None:
    bot = create_bot(client, auth_header, "ModeSwitch")
    switched = client.post(
        f"/v1/bots/{bot['id']}/computer",
        headers=auth_header,
        json={"bot_id": bot["id"], "mode": "dedicated"},
    )
    assert switched.status_code == 200
    assert switched.json()["computer_mode"] == "dedicated"
