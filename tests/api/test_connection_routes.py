from __future__ import annotations

import json

from tests.api.helpers import create_bot, wait_thread_has

SECRET = "ak-test-secret-wxyz"


def test_connections_require_auth_and_key(client, auth_header) -> None:
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
    bad = client.post(
        "/v1/connections",
        headers=auth_header,
        json={"provider": "mail", "redirect_url": "javascript:alert(1)"},
    )
    assert bad.status_code == 400
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
