from __future__ import annotations


def test_health_is_open_and_names_no_agent(client) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["db"] is True
    assert "agent_id" not in body
    assert "agentId" not in body


def test_v1_without_token_is_401(client) -> None:
    response = client.get("/v1/bots")
    assert response.status_code == 401


def test_v1_wrong_token_is_403(client) -> None:
    response = client.get("/v1/bots", headers={"Authorization": "Bearer not-the-host-token-value-xx"})
    assert response.status_code == 403


def test_pairing_requires_host_token(client) -> None:
    denied = client.post("/v1/devices/pairing")
    assert denied.status_code == 401
    device_token = client.post(
        "/v1/devices/pairing",
        headers={"Authorization": "Bearer not-the-host-token-value-xx"},
    )
    assert device_token.status_code == 403
