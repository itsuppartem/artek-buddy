from __future__ import annotations

import pytest
from tests.support import mask_secret

from artek_buddy.auth import PAIRING_ATTEMPT_LIMIT


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


def test_workspace_events_without_token_is_401(client) -> None:
    response = client.get("/v1/events")
    assert response.status_code == 401


def test_v1_wrong_token_is_403(client) -> None:
    response = client.get(
        "/v1/bots", headers={"Authorization": "Bearer not-the-host-token-value-xx"}
    )
    assert response.status_code == 403


def test_pairing_requires_host_token(client) -> None:
    denied = client.post("/v1/devices/pairing")
    assert denied.status_code == 401
    device_token = client.post(
        "/v1/devices/pairing",
        headers={"Authorization": "Bearer not-the-host-token-value-xx"},
    )
    assert device_token.status_code == 403


def test_me_is_the_owner(client, auth_header) -> None:
    response = client.get("/v1/me", headers=auth_header)
    assert response.status_code == 200
    body = response.json()
    assert body["user_id"] == "usr_owner"
    assert body["is_deployment_owner"] is True


@pytest.mark.no_model_seed
def test_models_lists_empty_without_keys(client, auth_header) -> None:
    response = client.get("/v1/models", headers=auth_header)
    assert response.status_code == 200
    assert response.json()["models"] == []


def test_session_get_and_create(client, auth_header) -> None:
    empty = client.get("/v1/session", headers=auth_header)
    assert empty.status_code == 200
    created = client.post("/v1/session", headers=auth_header, json={"name": "SessionBot"})
    assert created.status_code == 200
    body = created.json()
    assert body["bot_id"]
    assert body["thread_id"]
    listed = client.get("/v1/bots", headers=auth_header)
    assert any(bot["id"] == body["bot_id"] for bot in listed.json()["bots"])


def test_deployment_get_and_patch(client, auth_header) -> None:
    current = client.get("/v1/deployment", headers=auth_header)
    assert current.status_code == 200
    patched = client.patch(
        "/v1/deployment",
        headers=auth_header,
        json={"signups_enabled": False, "computer_host": "host"},
    )
    assert patched.status_code == 200
    assert patched.json()["signups_enabled"] is False
    assert patched.json()["computer_host"] == "host"


def test_host_can_create_device_without_pairing_code(client, auth_header) -> None:
    created = client.post(
        "/v1/devices",
        headers=auth_header,
        json={"name": "Host laptop", "platform": "linux"},
    )
    assert created.status_code == 200
    token = created.json()["token"]
    mask_secret(token)
    assert token.startswith("dev_")


def test_pairing_rate_limit_is_429(client) -> None:
    payload = {"name": "nope", "platform": "linux", "pairing_code": "ZZZZ-ZZZZ"}
    for _ in range(PAIRING_ATTEMPT_LIMIT):
        denied = client.post("/v1/devices", json=payload)
        assert denied.status_code == 403
    limited = client.post("/v1/devices", json=payload)
    assert limited.status_code == 429
