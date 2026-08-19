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

    stopped = client.post(f"/v1/computer/{bot_id}/stop", headers=auth_header)
    assert stopped.status_code == 200
    assert stopped.json()["state"] in {"stopped", "suspended"}


def test_computer_requires_auth(client) -> None:
    response = client.get("/v1/computer/bot_missing")
    assert response.status_code == 401
