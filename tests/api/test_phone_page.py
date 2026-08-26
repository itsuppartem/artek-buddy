from __future__ import annotations

import asyncio

import pytest
from fastapi import HTTPException

from artek_buddy.http.deps import _authorize_websocket
from tests.support import mask_secret


def _origin() -> dict[str, str]:
    return {"Origin": "http://testserver"}


def _mint(client, auth_header: dict[str, str]) -> str:
    minted = client.post("/v1/devices/pairing", headers=auth_header)
    assert minted.status_code == 200
    code = minted.json()["code"]
    mask_secret(code)
    return code


def _nonce(client) -> str:
    status = client.get("/local/status")
    assert status.status_code == 200
    nonce = status.json()["nonce"]
    assert nonce
    return nonce


def test_host_page_and_pairing_use_a_cookie_not_a_token_in_json(
    client, auth_header, tmp_path, monkeypatch
) -> None:
    web = tmp_path / "web"
    web.mkdir()
    (web / "index.html").write_text("<!doctype html><title>Artek Buddy</title>", encoding="utf-8")
    monkeypatch.setenv("ARTEK_WEB_ROOT", str(web))
    client.app.state.settings.web_root = str(web)

    page = client.get("/")
    assert page.status_code == 200
    assert "text/html" in page.headers["content-type"]
    assert "Artek Buddy" in page.text
    app_path = client.get("/app")
    assert app_path.status_code == 200
    assert "text/html" in app_path.headers["content-type"]

    empty = client.get("/local/status")
    assert empty.status_code == 200
    body = empty.json()
    assert body["paired"] is False
    assert body["surface"] == "host"
    assert "token" not in body

    missing = client.post(
        "/local/pair",
        headers={**_origin(), "X-Artek-Local-Nonce": _nonce(client)},
        json={"pairing_code": "ZZZZ-ZZZZ", "name": "Phone", "platform": "web"},
    )
    assert missing.status_code == 403

    paired = client.post(
        "/local/pair",
        headers={**_origin(), "X-Artek-Local-Nonce": _nonce(client)},
        json={"pairing_code": _mint(client, auth_header), "name": "Phone", "platform": "web"},
    )
    assert paired.status_code == 200
    payload = paired.json()
    assert payload["ok"] is True
    assert payload["paired"] is True
    assert "token" not in payload
    assert "token" not in (payload.get("device") or {})
    cookie = paired.cookies.get("artek_device")
    assert cookie
    mask_secret(cookie)
    assert cookie.startswith("dev_")
    assert cookie not in paired.text
    assert (payload.get("device") or {}).get("id", "").startswith("dev_")

    listed = client.get("/v1/bots")
    assert listed.status_code == 200
    assert "bots" in listed.json()

    owner = client.post(
        "/local/owner-read",
        headers={**_origin(), "X-Artek-Local-Nonce": _nonce(client)},
        json={"path": "/home/artek/notes.txt"},
    )
    assert owner.status_code == 403
    assert "Linux app" in owner.json()["detail"]

    forgotten = client.post(
        "/local/unpair",
        headers={**_origin(), "X-Artek-Local-Nonce": _nonce(client)},
    )
    assert forgotten.status_code == 200
    assert forgotten.json()["paired"] is False
    assert client.get("/v1/bots").status_code == 401


def test_host_cookie_is_not_the_host_token(client, auth_header) -> None:
    client.cookies.set("artek_device", client.app.state.settings.agent_http_token)
    denied = client.get("/v1/bots")
    assert denied.status_code == 401


def test_host_local_pair_needs_origin_and_nonce(client, auth_header) -> None:
    nonce = _nonce(client)
    body = {"pairing_code": _mint(client, auth_header), "name": "Phone", "platform": "web"}
    missing_origin = client.post(
        "/local/pair",
        headers={"X-Artek-Local-Nonce": nonce},
        json=body,
    )
    assert missing_origin.status_code == 403

    wrong_origin = client.post(
        "/local/pair",
        headers={"Origin": "https://evil.example", "X-Artek-Local-Nonce": nonce},
        json=body,
    )
    assert wrong_origin.status_code == 403

    bad_nonce = client.post(
        "/local/pair",
        headers={**_origin(), "X-Artek-Local-Nonce": "not-the-nonce"},
        json=body,
    )
    assert bad_nonce.status_code == 403


def test_novnc_websocket_accepts_pairing_cookie(client, auth_header) -> None:
    paired = client.post(
        "/local/pair",
        headers={**_origin(), "X-Artek-Local-Nonce": _nonce(client)},
        json={"pairing_code": _mint(client, auth_header), "name": "Phone", "platform": "web"},
    )
    assert paired.status_code == 200
    cookie = paired.cookies.get("artek_device")
    assert cookie
    mask_secret(cookie)

    class _Socket:
        def __init__(self, headers: dict[str, str]) -> None:
            self.headers = headers
            self.app = client.app

    missing = pytest.raises(HTTPException)
    with missing:
        asyncio.run(_authorize_websocket(_Socket({})))
    assert missing.value.status_code == 401

    actor = asyncio.run(_authorize_websocket(_Socket({"cookie": f"artek_device={cookie}"})))
    assert actor.startswith("dev_")

    host_token = client.app.state.settings.agent_http_token
    host_cookie = pytest.raises(HTTPException)
    with host_cookie:
        asyncio.run(_authorize_websocket(_Socket({"cookie": f"artek_device={host_token}"})))
    assert host_cookie.value.status_code == 401


def test_host_notify_is_not_a_desktop_alert(client) -> None:
    notify = client.post(
        "/local/notify",
        headers={**_origin(), "X-Artek-Local-Nonce": _nonce(client)},
        json={"title": "Hi", "body": "There", "urgency": "normal"},
    )
    assert notify.status_code == 200
    assert notify.json() == {"ok": False}
