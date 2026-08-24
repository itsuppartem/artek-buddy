from __future__ import annotations

import json
import sys
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from http.client import HTTPConnection
from pathlib import Path
from typing import Any

import pytest


def _proxy(client_mod: Any) -> Any:
    return sys.modules["proxy"]


@contextmanager
def running_proxy(
    client_mod: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Iterator[tuple[Any, int]]:
    proxy = _proxy(client_mod)
    (tmp_path / "index.html").write_text("<!doctype html>", encoding="utf-8")
    monkeypatch.setattr(proxy, "web_root", lambda: tmp_path)
    httpd = proxy.serve("http://127.0.0.1:8080", "dev_test", 0)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        yield httpd, int(httpd.server_address[1])
    finally:
        httpd.shutdown()
        httpd.server_close()


def _post_owner_exec(
    port: int, headers: dict[str, str], body: bytes
) -> tuple[int, list[tuple[str, str]]]:
    conn = HTTPConnection("127.0.0.1", port, timeout=5)
    try:
        conn.request("POST", "/local/owner-exec", body=body, headers=headers)
        resp = conn.getresponse()
        resp.read()
        return resp.status, resp.getheaders()
    finally:
        conn.close()


def _no_wildcard_cors(headers: list[tuple[str, str]]) -> None:
    allow = [value for name, value in headers if name.lower() == "access-control-allow-origin"]
    assert "*" not in allow


def test_local_rpc_origin_requires_loopback_origin(client_mod) -> None:
    assert client_mod.local_rpc_origin_allowed(None, "same-origin", 7777) is False
    assert client_mod.local_rpc_origin_allowed("http://127.0.0.1:7777", "same-origin", 7777) is True
    assert client_mod.local_rpc_origin_allowed("http://evil.example", "same-origin", 7777) is False
    assert client_mod.local_rpc_origin_allowed("http://127.0.0.1:7777", "cross-site", 7777) is False


def test_proxy_host_must_be_this_loopback_listener(client_mod) -> None:
    assert client_mod.proxy_host_allowed("127.0.0.1:7777", 7777) is True
    assert client_mod.proxy_host_allowed("localhost:7777", 7777) is True
    assert client_mod.proxy_host_allowed("evil.example:7777", 7777) is False
    assert client_mod.proxy_host_allowed(None, 7777) is False


def test_foreign_origin_owner_exec_does_not_run_subprocess(
    client_mod, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    proxy = _proxy(client_mod)
    called: list[int] = []

    def boom(*_args: object, **_kwargs: object) -> None:
        called.append(1)
        raise AssertionError("subprocess.run must not run")

    monkeypatch.setattr(proxy.subprocess, "run", boom)
    body = b'{"command":"true"}'
    with running_proxy(client_mod, tmp_path, monkeypatch) as (httpd, port):
        status, headers = _post_owner_exec(
            port,
            {
                "Host": f"127.0.0.1:{port}",
                "Origin": "https://evil.example",
                "Sec-Fetch-Site": "cross-site",
                "Content-Type": "application/json",
                "X-Artek-Local-Nonce": httpd.local_nonce,
            },
            body,
        )
    assert status == 403
    _no_wildcard_cors(headers)
    assert called == []


def test_missing_origin_owner_exec_is_forbidden(
    client_mod, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    proxy = _proxy(client_mod)
    called: list[int] = []
    monkeypatch.setattr(proxy.subprocess, "run", lambda *_a, **_k: called.append(1))
    body = b'{"command":"true"}'
    with running_proxy(client_mod, tmp_path, monkeypatch) as (httpd, port):
        status, headers = _post_owner_exec(
            port,
            {
                "Host": f"127.0.0.1:{port}",
                "Content-Type": "application/json",
                "X-Artek-Local-Nonce": httpd.local_nonce,
            },
            body,
        )
    assert status == 403
    _no_wildcard_cors(headers)
    assert called == []


def test_wrong_host_owner_exec_is_forbidden(
    client_mod, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    proxy = _proxy(client_mod)
    called: list[int] = []
    monkeypatch.setattr(proxy.subprocess, "run", lambda *_a, **_k: called.append(1))
    body = b'{"command":"true"}'
    with running_proxy(client_mod, tmp_path, monkeypatch) as (httpd, port):
        origin = f"http://127.0.0.1:{port}"
        status, headers = _post_owner_exec(
            port,
            {
                "Host": "evil.example:80",
                "Origin": origin,
                "Content-Type": "application/json",
                "X-Artek-Local-Nonce": httpd.local_nonce,
            },
            body,
        )
    assert status == 403
    _no_wildcard_cors(headers)
    assert called == []


def test_oversized_local_json_is_rejected_without_exec(
    client_mod, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    proxy = _proxy(client_mod)
    called: list[int] = []
    monkeypatch.setattr(proxy.subprocess, "run", lambda *_a, **_k: called.append(1))
    body = b"x" * (proxy.LOCAL_JSON_MAX + 1)
    with running_proxy(client_mod, tmp_path, monkeypatch) as (httpd, port):
        origin = f"http://127.0.0.1:{port}"
        status, headers = _post_owner_exec(
            port,
            {
                "Host": f"127.0.0.1:{port}",
                "Origin": origin,
                "Content-Type": "application/json",
                "X-Artek-Local-Nonce": httpd.local_nonce,
            },
            body,
        )
    assert status == 413
    _no_wildcard_cors(headers)
    assert called == []


def test_status_issues_nonce_only_to_this_origin(
    client_mod, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with running_proxy(client_mod, tmp_path, monkeypatch) as (httpd, port):
        origin = f"http://127.0.0.1:{port}"
        ok = HTTPConnection("127.0.0.1", port, timeout=5)
        denied = HTTPConnection("127.0.0.1", port, timeout=5)
        try:
            ok.request("GET", "/local/status", headers={"Origin": origin})
            good = ok.getresponse()
            payload = json.loads(good.read().decode("utf-8"))
            denied.request("GET", "/local/status", headers={"Origin": "https://evil.example"})
            bad = denied.getresponse()
            bad.read()
        finally:
            ok.close()
            denied.close()
    assert good.status == 200
    assert payload["nonce"] == httpd.local_nonce
    assert bad.status == 403
