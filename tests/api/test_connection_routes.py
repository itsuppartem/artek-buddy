from __future__ import annotations

import json
import time

from fastapi.testclient import TestClient
from tests.api.helpers import create_bot, wait_thread_has

from artek_buddy.connections.broker import fake_broker

SECRET = "ak-test-secret-wxyz"
HOST_CALLBACK = "https://host.example/v1/connections/callback"


def test_connections_require_auth_and_key(client, auth_header) -> None:
    assert client.post("/v1/connections/key", json={"api_key": "x"}).status_code == 401
    assert (
        client.post(
            "/v1/connections/key",
            headers={"Authorization": "Bearer nope"},
            json={"api_key": "x"},
        ).status_code
        == 403
    )
    assert client.get("/v1/connections/status").status_code == 401
    assert (
        client.get("/v1/connections/catalog", headers={"Authorization": "Bearer nope"}).status_code
        == 403
    )
    missing = client.get("/v1/connections/catalog", headers=auth_header)
    assert missing.status_code == 409
    assert missing.json()["detail"] == "paste a key in Plugins"
    empty = client.post("/v1/connections/key", headers=auth_header, json={"api_key": "   "})
    assert empty.status_code == 400
    assert empty.json()["detail"] == "API key is empty"


def test_save_key_catalog_connect_tool_revoke_never_echoes(client, auth_header) -> None:
    saved = client.post("/v1/connections/key", headers=auth_header, json={"api_key": SECRET})
    assert saved.status_code == 200
    body = saved.json()
    assert body["configured"] is True
    assert body["last_four"] == "wxyz"
    blob = json.dumps(body)
    assert SECRET not in blob
    assert "api_key" not in blob

    status = client.get("/v1/connections/status", headers=auth_header)
    assert status.status_code == 200
    assert status.json()["configured"] is True
    assert SECRET not in json.dumps(status.json())

    catalog = client.get("/v1/connections/catalog?q=docs", headers=auth_header)
    assert catalog.status_code == 200
    items = catalog.json()["items"]
    assert [item["slug"] for item in items] == ["docs"]
    assert items[0]["name"] == "Docs"
    assert items[0]["no_auth"] is True
    assert items[0]["connected"] is False

    began = client.post(
        "/v1/connections",
        headers=auth_header,
        json={"provider": "docs", "redirect_url": "https://window.example/app"},
    )
    assert began.status_code == 200
    connection = began.json()["connection"]
    assert began.json()["authorization_url"] is None
    assert connection["provider"] == "docs"
    assert connection["status"] == "connected"
    assert "docs_read" in connection["capabilities"]
    assert SECRET not in json.dumps(began.json())

    listed = client.get("/v1/connections", headers=auth_header)
    assert listed.status_code == 200
    assert [row["provider"] for row in listed.json()["connections"]] == ["docs"]

    bot = create_bot(client, auth_header, "PlugDocs")
    sent = client.post(
        f"/v1/threads/{bot['id']}/messages",
        headers=auth_header,
        json={"text": "please use Docs"},
    )
    assert sent.status_code == 200
    answered = wait_thread_has(client, auth_header, bot["id"], "Subotica")
    blob = json.dumps(answered)
    assert "please use Docs" in blob
    plugin_blocks = [
        block
        for message in answered.get("messages") or []
        for block in message.get("blocks") or []
        if block.get("kind") == "plugin"
    ]
    assert plugin_blocks
    assert plugin_blocks[0]["name"] == "Docs"
    assert "Subotica" in plugin_blocks[0]["text"]

    revoked = client.post(
        f"/v1/connections/{connection['id']}/revoke",
        headers=auth_header,
    )
    assert revoked.status_code == 200
    after = client.get("/v1/connections", headers=auth_header)
    assert after.json()["connections"][0]["status"] == "revoked"
    catalog_after = client.get("/v1/connections/catalog?q=docs", headers=auth_header)
    assert catalog_after.json()["items"][0]["connected"] is False

    silent = create_bot(client, auth_header, "PlugSilent")
    again = client.post(
        f"/v1/threads/{silent['id']}/messages",
        headers=auth_header,
        json={"text": "please e2e-plugin-docs"},
    )
    assert again.status_code == 200
    snap = wait_thread_has(client, auth_header, silent["id"], "please e2e-plugin-docs")
    assert "Subotica" not in json.dumps(snap)

    forgotten = client.delete("/v1/connections/key", headers=auth_header)
    assert forgotten.status_code == 200
    assert client.get("/v1/connections/catalog", headers=auth_header).status_code == 409
    assert SECRET not in json.dumps(
        client.get("/v1/connections/status", headers=auth_header).json()
    )


def test_connection_begin_rejects_unknown_self_and_bad_redirect(client, auth_header) -> None:
    client.post("/v1/connections/key", headers=auth_header, json={"api_key": SECRET})
    missing = client.post(
        "/v1/connections",
        headers=auth_header,
        json={"provider": "nope", "redirect_url": "https://window.example/app"},
    )
    assert missing.status_code == 404
    first = client.post(
        "/v1/connections",
        headers=auth_header,
        json={"provider": "mail", "redirect_url": "https://window.example/app"},
    )
    assert first.status_code == 200
    assert first.json()["connection"]["status"] == "pending"
    assert first.json()["authorization_url"]
    repeat = client.post(
        "/v1/connections",
        headers=auth_header,
        json={"provider": "mail", "redirect_url": "https://window.example/app"},
    )
    assert repeat.status_code == 409
    finished = client.post(
        f"/v1/connections/{first.json()['connection']['id']}/complete",
        headers=auth_header,
    )
    assert finished.status_code == 200
    assert finished.json()["status"] == "connected"
    assert "mail_inbox" in finished.json()["capabilities"]
    assert fake_broker().last_callback == HOST_CALLBACK


def test_connection_begin_ignores_caller_redirect(client, auth_header) -> None:
    """http, evil host, extra port, and a lookalike host cannot become callback_url (#369)."""
    client.post("/v1/connections/key", headers=auth_header, json={"api_key": SECRET})
    for redirect in (
        "http://host.example/app",
        "https://evil.example",
        "https://host.example:8443/app",
        "https://host.example.evil.example/app",
        "javascript:alert(1)",
    ):
        started = client.post(
            "/v1/connections",
            headers=auth_header,
            json={"provider": "docs", "redirect_url": redirect},
        )
        assert started.status_code == 200, redirect
        assert fake_broker().last_callback == HOST_CALLBACK
        client.post(
            f"/v1/connections/{started.json()['connection']['id']}/revoke",
            headers=auth_header,
        )


def test_store_seeds_plugins_key_once(client, auth_header) -> None:
    store = client.app.state.store
    store.clear_connections()
    store.seed_env_connection_key("ak-env-seed-abcd")
    status = client.get("/v1/connections/status", headers=auth_header)
    assert status.status_code == 200
    assert status.json()["configured"] is True
    assert status.json()["last_four"] == "abcd"
    assert "ak-env-seed-abcd" not in json.dumps(status.json())
    store.seed_env_connection_key("ak-other-zzzz")
    again = client.get("/v1/connections/status", headers=auth_header)
    assert again.json()["last_four"] == "abcd"


def test_lifespan_seeds_plugins_key(client, monkeypatch, auth_header) -> None:
    client.app.state.store.clear_connections()
    monkeypatch.setenv("COMPOSIO_API_KEY", "ak-env-seed-env1")

    from artek_buddy.main import app

    with TestClient(app) as session:
        status = session.get("/v1/connections/status", headers=auth_header)
        assert status.status_code == 200
        assert status.json()["configured"] is True
        assert status.json()["last_four"] == "env1"
        assert "ak-env-seed-env1" not in json.dumps(status.json())


def _plugin_blocks(snap: dict) -> list[dict]:
    return [
        block
        for message in snap.get("messages") or []
        for block in message.get("blocks") or []
        if block.get("kind") == "plugin"
    ]


def wait_plugin_text(client, auth_header, bot_id: str, needle: str, timeout: float = 15.0) -> dict:
    deadline = time.time() + timeout
    last: dict = {}
    while time.time() < deadline:
        snap = client.get(f"/v1/threads/{bot_id}", headers=auth_header)
        assert snap.status_code == 200, snap.text
        last = snap.json()
        for block in _plugin_blocks(last):
            blob = f"{block.get('text') or ''} {block.get('url') or ''} {block.get('name') or ''}"
            if needle.lower() in blob.lower():
                return last
        time.sleep(0.1)
    raise AssertionError(f"{bot_id} never showed plugin {needle!r}: {_plugin_blocks(last)}")


def test_connect_app_from_chat_then_use_docs(client, auth_header) -> None:
    client.post("/v1/connections/key", headers=auth_header, json={"api_key": SECRET})
    bot = create_bot(client, auth_header, "ChatDocs")
    sent = client.post(
        f"/v1/threads/{bot['id']}/messages",
        headers=auth_header,
        json={"text": "please e2e-connect-docs"},
    )
    assert sent.status_code == 200
    snap = wait_plugin_text(client, auth_header, bot["id"], "Connected")
    cards = _plugin_blocks(snap)
    assert cards[0]["name"] == "Docs"
    assert not cards[0].get("url")

    used = client.post(
        f"/v1/threads/{bot['id']}/messages",
        headers=auth_header,
        json={"text": "please use Docs"},
    )
    assert used.status_code == 200
    answered = wait_thread_has(client, auth_header, bot["id"], "Subotica")
    docs = _plugin_blocks(answered)
    assert docs[-1]["name"] == "Docs"
    assert "Subotica" in docs[-1]["text"]

    again = client.post(
        f"/v1/threads/{bot['id']}/messages",
        headers=auth_header,
        json={"text": "please e2e-connect-docs"},
    )
    assert again.status_code == 200
    twice = wait_plugin_text(client, auth_header, bot["id"], "already")
    assert twice


def test_list_apps_and_connect_fail_without_key(client, auth_header) -> None:
    bot = create_bot(client, auth_header, "ChatNoKey")
    listed = client.post(
        f"/v1/threads/{bot['id']}/messages",
        headers=auth_header,
        json={"text": "please e2e-list-apps"},
    )
    assert listed.status_code == 200
    wait_thread_has(client, auth_header, bot["id"], "paste a key")
    assert client.get("/v1/connections", headers=auth_header).status_code == 409
    missing = client.post(
        f"/v1/threads/{bot['id']}/messages",
        headers=auth_header,
        json={"text": "please e2e-connect-docs"},
    )
    assert missing.status_code == 200
    wait_thread_has(client, auth_header, bot["id"], "paste a key")


def test_connect_app_oauth_puts_login_url_on_the_card(client, auth_header) -> None:
    client.post("/v1/connections/key", headers=auth_header, json={"api_key": SECRET})
    bot = create_bot(client, auth_header, "ChatMail")
    sent = client.post(
        f"/v1/threads/{bot['id']}/messages",
        headers=auth_header,
        json={"text": "please e2e-connect-mail"},
    )
    assert sent.status_code == 200
    snap = wait_thread_has(client, auth_header, bot["id"], "I'll attach Mail.")
    cards = _plugin_blocks(snap)
    assert cards
    assert cards[0]["name"] == "Mail"
    assert cards[0].get("url")
    assert "example.test" in cards[0]["url"]
    listed = client.get("/v1/connections", headers=auth_header)
    assert listed.json()["connections"][0]["status"] == "pending"
    assert fake_broker().last_callback == HOST_CALLBACK
    assert fake_broker().last_callback != "https://window.example/app"


def test_connect_unknown_app_fails_closed(client, auth_header) -> None:
    client.post("/v1/connections/key", headers=auth_header, json={"api_key": SECRET})
    bot = create_bot(client, auth_header, "ChatNope")
    sent = client.post(
        f"/v1/threads/{bot['id']}/messages",
        headers=auth_header,
        json={"text": "please e2e-connect-nope"},
    )
    assert sent.status_code == 200
    wait_thread_has(client, auth_header, bot["id"], "app not found")


def test_connect_start_fail_explains_the_next_step(client, auth_header) -> None:
    client.post("/v1/connections/key", headers=auth_header, json={"api_key": SECRET})
    failed = client.post(
        "/v1/connections",
        headers=auth_header,
        json={"provider": "needssetup", "redirect_url": "https://window.example/app"},
    )
    assert failed.status_code == 502
    detail = failed.json()["detail"]
    assert "could not start that connection" in detail
    assert "finish that setup" in detail
    assert "try Connect again" in detail
    assert detail != "could not start that connection"
