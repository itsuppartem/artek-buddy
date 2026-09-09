from __future__ import annotations

import pytest

from artek_buddy.connections.http import HttpBroker


class _Resp:
    def __init__(self, status_code: int, payload: dict) -> None:
        self.status_code = status_code
        self._payload = payload

    def json(self) -> dict:
        return self._payload


def test_begin_uses_catalog_no_auth_when_toolkit_omits_it(monkeypatch) -> None:
    broker = HttpBroker("ak-test")

    def fake_request(method: str, path: str, **kwargs):
        if method == "GET" and path == "/toolkits/weather":
            return _Resp(200, {"slug": "weather", "name": "Weather"})
        if method == "GET" and path == "/toolkits":
            return _Resp(
                200,
                {"items": [{"slug": "weather", "name": "Weather", "no_auth": True}]},
            )
        if method == "GET" and path == "/tools":
            return _Resp(200, {"items": []})
        raise AssertionError((method, path, kwargs))

    monkeypatch.setattr(broker, "_request", fake_request)
    started = broker.begin("weather", "https://window.example/app")
    assert started.status == "connected"
    assert started.no_auth is True
    assert started.authorization_url is None


def test_begin_auth_config_failure_explains_the_next_step(monkeypatch) -> None:
    broker = HttpBroker("ak-test")

    def fake_request(method: str, path: str, **kwargs):
        if method == "GET" and path == "/toolkits/mail":
            return _Resp(200, {"slug": "mail", "name": "Mail"})
        if method == "GET" and path == "/toolkits":
            return _Resp(200, {"items": [{"slug": "mail", "name": "Mail", "no_auth": False}]})
        if method == "GET" and path == "/auth_configs":
            return _Resp(200, {"items": []})
        if method == "POST" and path == "/auth_configs":
            return _Resp(400, {"error": "no managed auth"})
        raise AssertionError((method, path, kwargs))

    monkeypatch.setattr(broker, "_request", fake_request)
    with pytest.raises(RuntimeError, match="finish that setup"):
        broker.begin("mail", "https://window.example/app")
