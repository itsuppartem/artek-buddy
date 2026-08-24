from __future__ import annotations

import json

import pytest
from tests.api.helpers import create_bot, message_texts

from artek_buddy.model_catalog import NEEDS_MODEL_TEXT

pytestmark = pytest.mark.no_model_seed

SECRET = "sk-test-secret-wxyz"


def test_credentials_start_empty_and_models_list_is_empty(client, auth_header) -> None:
    listed = client.get("/v1/models/credentials", headers=auth_header)
    assert listed.status_code == 200
    body = listed.json()
    assert [row["provider"] for row in body["credentials"]] == [
        "cursor",
        "openrouter",
        "openai",
        "anthropic",
        "xai",
    ]
    assert all(row["has_key"] is False for row in body["credentials"])
    assert all(not row.get("last_four") for row in body["credentials"])
    assert body["default_provider"] is None
    assert body["default_model"] is None
    assert SECRET not in json.dumps(body)
    assert "api_key" not in json.dumps(body)

    models = client.get("/v1/models", headers=auth_header)
    assert models.status_code == 200
    assert models.json()["models"] == []


def test_connect_list_default_forget_and_never_echoes_key(client, auth_header) -> None:
    connected = client.post(
        "/v1/models/credentials",
        headers=auth_header,
        json={"provider": "openrouter", "api_key": SECRET},
    )
    assert connected.status_code == 200
    row = connected.json()
    assert row["provider"] == "openrouter"
    assert row["has_key"] is True
    assert row["last_four"] == "wxyz"
    assert SECRET not in json.dumps(row)
    assert "api_key" not in row

    listed = client.get("/v1/models/credentials", headers=auth_header)
    assert listed.status_code == 200
    blob = json.dumps(listed.json())
    assert SECRET not in blob
    assert "api_key" not in blob
    openrouter = next(
        item for item in listed.json()["credentials"] if item["provider"] == "openrouter"
    )
    assert openrouter["last_four"] == "wxyz"
    assert openrouter["has_key"] is True

    models = client.get("/v1/models", headers=auth_header)
    assert models.status_code == 200
    assert models.json()["models"] == [{"id": "scripted", "provider": "openrouter"}]

    missing = client.post(
        "/v1/models/default",
        headers=auth_header,
        json={"provider": "openrouter", "model": "not-on-the-list"},
    )
    assert missing.status_code == 400

    chosen = client.post(
        "/v1/models/default",
        headers=auth_header,
        json={"provider": "openrouter", "model": "scripted"},
    )
    assert chosen.status_code == 200
    after = client.get("/v1/models/credentials", headers=auth_header)
    assert after.json()["default_provider"] == "openrouter"
    assert after.json()["default_model"] == "scripted"

    forgotten = client.delete("/v1/models/credentials/openrouter", headers=auth_header)
    assert forgotten.status_code == 200
    empty = client.get("/v1/models/credentials", headers=auth_header)
    openrouter = next(
        item for item in empty.json()["credentials"] if item["provider"] == "openrouter"
    )
    assert openrouter["has_key"] is False
    assert not openrouter.get("last_four")
    assert empty.json()["default_model"] is None
    assert client.get("/v1/models", headers=auth_header).json()["models"] == []
    assert SECRET not in json.dumps(empty.json())


def test_connect_cursor_uses_scripted_catalog(client, auth_header) -> None:
    connected = client.post(
        "/v1/models/credentials",
        headers=auth_header,
        json={"provider": "cursor", "api_key": SECRET},
    )
    assert connected.status_code == 200
    assert connected.json()["provider"] == "cursor"
    assert connected.json()["has_key"] is True
    assert connected.json()["last_four"] == "wxyz"
    models = client.get("/v1/models", headers=auth_header)
    assert models.status_code == 200
    assert models.json()["models"] == [{"id": "scripted", "provider": "cursor"}]


def test_send_without_default_does_not_start_a_turn(client, auth_header) -> None:
    bot = create_bot(client, auth_header, "NeedModel")
    sent = client.post(
        f"/v1/threads/{bot['id']}/messages",
        headers=auth_header,
        json={"text": "hello"},
    )
    assert sent.status_code == 200
    snap = client.get(f"/v1/threads/{bot['id']}", headers=auth_header)
    assert snap.status_code == 200
    assert snap.json()["run"] is None
    texts = message_texts(snap.json())
    assert "hello" in texts
    assert NEEDS_MODEL_TEXT in texts


def test_me_needs_model_until_default_is_set(client, auth_header) -> None:
    empty = client.get("/v1/me", headers=auth_header)
    assert empty.status_code == 200
    assert empty.json()["needs_model"] is True
    client.post(
        "/v1/models/credentials",
        headers=auth_header,
        json={"provider": "openai", "api_key": SECRET},
    )
    client.post(
        "/v1/models/default",
        headers=auth_header,
        json={"provider": "openai", "model": "scripted"},
    )
    ready = client.get("/v1/me", headers=auth_header)
    assert ready.json()["needs_model"] is False
    assert ready.json()["default_provider"] == "openai"
    assert ready.json()["default_model"] == "scripted"
