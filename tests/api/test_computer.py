from __future__ import annotations

from tests.api.helpers import create_bot


def test_computer_boot_stop_on_fake(client, auth_header) -> None:
    bot = client.post(
        "/v1/bots",
        headers=auth_header,
        json={"name": "Desk", "computer_mode": "dedicated"},
    )
    bot_id = bot.json()["id"]
    status = client.get(f"/v1/computer/{bot_id}", headers=auth_header)
    assert status.status_code == 200
    assert status.json()["kind"] in {"fake", "docker", "desktop"}

    booted = client.post(f"/v1/computer/{bot_id}/boot", headers=auth_header)
    assert booted.status_code == 200
    assert booted.json()["state"] == "running"

    screen = client.get(f"/v1/computer/{bot_id}/screen", headers=auth_header)
    assert screen.status_code == 200
    assert screen.json()["url"] is None

    stopped = client.post(f"/v1/computer/{bot_id}/stop", headers=auth_header)
    assert stopped.status_code == 200
    assert stopped.json()["state"] == "suspended"


def test_computer_restart_and_reset(client, auth_header) -> None:
    bot_id = create_bot(client, auth_header, "RestartBox", computer_mode="dedicated")["id"]
    booted = client.post(f"/v1/computer/{bot_id}/boot", headers=auth_header)
    assert booted.status_code == 200
    restarted = client.post(f"/v1/computer/{bot_id}/restart", headers=auth_header)
    assert restarted.status_code == 200
    assert restarted.json()["state"] == "running"
    reset = client.post(f"/v1/computer/{bot_id}/reset", headers=auth_header)
    assert reset.status_code == 200
    assert reset.json()["state"] == "stopped"


def test_team_status_names_the_bot_that_booted(client, auth_header) -> None:
    alpha = client.post(
        "/v1/bots",
        headers=auth_header,
        json={"name": "AlphaHold", "computer_mode": "team"},
    )
    bravo = client.post(
        "/v1/bots",
        headers=auth_header,
        json={"name": "BravoWait", "computer_mode": "team"},
    )
    assert alpha.status_code == 200
    assert bravo.status_code == 200
    alpha_id = alpha.json()["id"]
    bravo_id = bravo.json()["id"]

    booted = client.post(f"/v1/computer/{alpha_id}/boot", headers=auth_header)
    assert booted.status_code == 200
    taken = client.post(f"/v1/computer/{alpha_id}/takeover", headers=auth_header)
    assert taken.status_code == 200

    waiting = client.get(f"/v1/computer/{bravo_id}", headers=auth_header)
    assert waiting.status_code == 200
    body = waiting.json()
    assert body["state"] == "running"
    assert body["busy_bot_name"] == "AlphaHold"
    assert body["control_holder"] != "user"

    blocked = client.post(f"/v1/computer/{bravo_id}/reset", headers=auth_header)
    assert blocked.status_code == 409


def test_computer_files_and_path_jail(client, auth_header) -> None:
    bot_id = create_bot(client, auth_header, "FilesBox", computer_mode="dedicated")["id"]
    booted = client.post(f"/v1/computer/{bot_id}/boot", headers=auth_header)
    assert booted.status_code == 200
    listed = client.get(f"/v1/computer/{bot_id}/files", headers=auth_header)
    assert listed.status_code == 200
    assert "entries" in listed.json()
    escaped = client.get(f"/v1/computer/{bot_id}/files", headers=auth_header, params={"path": "../secret"})
    assert escaped.status_code == 400
    missing = client.get(
        f"/v1/computer/{bot_id}/files/read",
        headers=auth_header,
        params={"path": "no-such-file.txt"},
    )
    assert missing.status_code == 400


def test_computer_input_needs_takeover(client, auth_header) -> None:
    bot_id = create_bot(client, auth_header, "InputBox", computer_mode="dedicated")["id"]
    booted = client.post(f"/v1/computer/{bot_id}/boot", headers=auth_header)
    assert booted.status_code == 200
    denied = client.post(
        f"/v1/computer/{bot_id}/input",
        headers=auth_header,
        json={"kind": "key", "payload": {"text": "a"}},
    )
    assert denied.status_code == 400
    taken = client.post(f"/v1/computer/{bot_id}/takeover", headers=auth_header)
    assert taken.status_code == 200
    typed = client.post(
        f"/v1/computer/{bot_id}/input",
        headers=auth_header,
        json={"kind": "key", "payload": {"text": "a"}},
    )
    assert typed.status_code == 200
    beat = client.post(f"/v1/computer/{bot_id}/heartbeat", headers=auth_header)
    assert beat.status_code == 200
    released = client.post(f"/v1/computer/{bot_id}/release", headers=auth_header)
    assert released.status_code == 200
    assert released.json()["ok"] is True
    after = client.get(f"/v1/computer/{bot_id}", headers=auth_header)
    assert after.status_code == 200
    assert after.json()["control_holder"] != "user"


def test_computer_requires_auth(client) -> None:
    response = client.get("/v1/computer/bot_missing")
    assert response.status_code == 401
