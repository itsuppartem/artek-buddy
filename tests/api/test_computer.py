from __future__ import annotations


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
    assert stopped.json()["state"] in {"stopped", "suspended"}


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


def test_computer_requires_auth(client) -> None:
    response = client.get("/v1/computer/bot_missing")
    assert response.status_code == 401
