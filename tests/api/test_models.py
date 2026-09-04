from __future__ import annotations

import json

import pytest
from tests.api.helpers import (
    create_bot,
    message_metas,
    message_texts,
    wait_run,
    wait_run_status,
    wait_thread_has,
)

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


def test_model_key_routes_exist(client) -> None:
    missing = client.post(
        "/v1/models/credentials",
        json={"provider": "cursor", "api_key": "x"},
    )
    assert missing.status_code == 401
    listed = client.get("/v1/models/credentials")
    assert listed.status_code == 401
    default = client.post(
        "/v1/models/default",
        json={"provider": "cursor", "model": "scripted"},
    )
    assert default.status_code == 401
    bad = {"Authorization": "Bearer nope"}
    refused = client.post(
        "/v1/models/credentials",
        headers=bad,
        json={"provider": "cursor", "api_key": "x"},
    )
    assert refused.status_code == 403


def test_connect_empty_key_is_400(client, auth_header) -> None:
    empty = client.post(
        "/v1/models/credentials",
        headers=auth_header,
        json={"provider": "cursor", "api_key": "   "},
    )
    assert empty.status_code == 400
    assert empty.json()["detail"] == "API key is empty"
    placeholder = client.post(
        "/v1/models/credentials",
        headers=auth_header,
        json={"provider": "cursor", "api_key": "crsr_your_key_here"},
    )
    assert placeholder.status_code == 400
    assert placeholder.json()["detail"] == "API key is empty"


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
    assert listed.json()["default_provider"] == "openrouter"
    assert listed.json()["default_model"] == "scripted"

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
    listed = client.get("/v1/models/credentials", headers=auth_header)
    assert listed.status_code == 200
    body = listed.json()
    assert body["default_provider"] == "cursor"
    assert body["default_model"] == "scripted"
    assert body["default_effort"] == "xhigh"
    assert body["default_fast"] is True


def test_set_default_persists_effort_and_fast(client, auth_header) -> None:
    client.post(
        "/v1/models/credentials",
        headers=auth_header,
        json={"provider": "openrouter", "api_key": SECRET},
    )
    chosen = client.post(
        "/v1/models/default",
        headers=auth_header,
        json={"provider": "openrouter", "model": "scripted", "effort": "high", "fast": False},
    )
    assert chosen.status_code == 200
    after = client.get("/v1/models/credentials", headers=auth_header)
    assert after.json()["default_effort"] == "high"
    assert after.json()["default_fast"] is False
    kept = client.post(
        "/v1/models/default",
        headers=auth_header,
        json={"provider": "openrouter", "model": "scripted"},
    )
    assert kept.status_code == 200
    same = client.get("/v1/models/credentials", headers=auth_header)
    assert same.json()["default_effort"] == "high"
    assert same.json()["default_fast"] is False


def test_set_default_writes_meta_and_does_not_cancel_a_live_run(client, auth_header) -> None:
    from artek_buddy.model_switch import default_model_line

    client.post(
        "/v1/models/credentials",
        headers=auth_header,
        json={"provider": "cursor", "api_key": SECRET},
    )
    bot_id = create_bot(client, auth_header, "ModelNote")["id"]
    sent = client.post(
        f"/v1/threads/{bot_id}/messages",
        headers=auth_header,
        json={"text": "please e2e-hang now"},
    )
    assert sent.status_code == 200
    wait_run_status(client, auth_header, bot_id, sent.json()["run_id"], "running")
    chosen = client.post(
        "/v1/models/default",
        headers=auth_header,
        json={
            "provider": "cursor",
            "model": "scripted",
            "effort": "low",
            "fast": True,
            "bot_id": bot_id,
        },
    )
    assert chosen.status_code == 200
    snap = client.get(f"/v1/threads/{bot_id}", headers=auth_header)
    assert snap.status_code == 200
    body = snap.json()
    assert body["run"]["status"] == "running"
    assert body["run"]["id"] == sent.json()["run_id"]
    assert default_model_line("scripted", "low", True, live=True) in message_metas(body)


def _agent_id(client, auth_header: dict[str, str], bot_id: str) -> str:
    row = client.get(f"/v1/bots/{bot_id}", headers=auth_header)
    assert row.status_code == 200, row.text
    value = row.json().get("cursor_agent_id") or row.json().get("cursorAgentId")
    assert value
    return str(value)


def _connect_cursor(client, auth_header: dict[str, str]) -> None:
    connected = client.post(
        "/v1/models/credentials",
        headers=auth_header,
        json={"provider": "cursor", "api_key": SECRET},
    )
    assert connected.status_code == 200


def test_first_send_keeps_the_session_when_the_model_did_not_change(client, auth_header) -> None:
    _connect_cursor(client, auth_header)
    bot_id = create_bot(client, auth_header, "KeepSession")["id"]
    before = _agent_id(client, auth_header, bot_id)
    sent = client.post(
        f"/v1/threads/{bot_id}/messages",
        headers=auth_header,
        json={"text": "hello"},
    )
    assert sent.status_code == 200
    wait_run(client, auth_header, bot_id, sent.json()["run_id"])
    assert _agent_id(client, auth_header, bot_id) == before


def test_unchecking_fast_on_an_idle_chat_starts_a_new_session(client, auth_header) -> None:
    _connect_cursor(client, auth_header)
    bot_id = create_bot(client, auth_header, "FastIdle")["id"]
    sent = client.post(
        f"/v1/threads/{bot_id}/messages",
        headers=auth_header,
        json={"text": "hello"},
    )
    assert sent.status_code == 200
    wait_run(client, auth_header, bot_id, sent.json()["run_id"])
    before = _agent_id(client, auth_header, bot_id)
    chosen = client.post(
        "/v1/models/default",
        headers=auth_header,
        json={
            "provider": "cursor",
            "model": "scripted",
            "effort": "xhigh",
            "fast": False,
            "bot_id": bot_id,
        },
    )
    assert chosen.status_code == 200
    listed = client.get("/v1/models/credentials", headers=auth_header)
    assert listed.json()["default_fast"] is False
    assert _agent_id(client, auth_header, bot_id) != before


def test_unchecking_fast_during_a_live_turn_starts_a_new_session_on_the_follow_up(
    client, auth_header
) -> None:
    _connect_cursor(client, auth_header)
    bot_id = create_bot(client, auth_header, "FastLive")["id"]
    sent = client.post(
        f"/v1/threads/{bot_id}/messages",
        headers=auth_header,
        json={"text": "please e2e-slow now"},
    )
    assert sent.status_code == 200
    wait_run_status(client, auth_header, bot_id, sent.json()["run_id"], "running")
    before = _agent_id(client, auth_header, bot_id)
    chosen = client.post(
        "/v1/models/default",
        headers=auth_header,
        json={
            "provider": "cursor",
            "model": "scripted",
            "effort": "xhigh",
            "fast": False,
            "bot_id": bot_id,
        },
    )
    assert chosen.status_code == 200
    queued = client.post(
        f"/v1/threads/{bot_id}/messages",
        headers=auth_header,
        json={"text": "hello after fast off"},
    )
    assert queued.status_code == 200
    assert queued.json().get("queued") is True
    assert _agent_id(client, auth_header, bot_id) == before
    wait_run(client, auth_header, bot_id, sent.json()["run_id"])
    wait_thread_has(client, auth_header, bot_id, "ok")
    assert _agent_id(client, auth_header, bot_id) != before


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
    ready = client.get("/v1/me", headers=auth_header)
    assert ready.json()["needs_model"] is False
    assert ready.json()["default_provider"] == "openai"
    assert ready.json()["default_model"] == "scripted"
