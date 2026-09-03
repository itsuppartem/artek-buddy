from __future__ import annotations

import json
import sys
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from http.client import HTTPConnection
from pathlib import Path
from types import SimpleNamespace
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
    assert (
        client_mod.local_rpc_origin_allowed(None, "same-origin", 7777, require_origin=False) is True
    )
    assert (
        client_mod.local_rpc_origin_allowed(None, "cross-site", 7777, require_origin=False) is False
    )
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


def test_owner_exec_uses_opt_in_ssh_mux_environment(
    client_mod, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    proxy = _proxy(client_mod)
    captured: list[dict[str, str]] = []
    monkeypatch.setattr(
        proxy,
        "owner_exec_environment",
        lambda: {"ARTEK_SSH_CONTROL_PATH": "/tmp/artek-test/%C"},
    )
    monkeypatch.setattr(
        proxy.subprocess,
        "run",
        lambda *_args, **kwargs: (
            captured.append(kwargs["env"]) or SimpleNamespace(stdout="", stderr="", returncode=0)
        ),
    )
    body = b'{"command":"ssh owner-host uname"}'
    with running_proxy(client_mod, tmp_path, monkeypatch) as (httpd, port):
        origin = f"http://127.0.0.1:{port}"
        status, _headers = _post_owner_exec(
            port,
            {
                "Host": f"127.0.0.1:{port}",
                "Origin": origin,
                "Content-Type": "application/json",
                "X-Artek-Local-Nonce": httpd.local_nonce,
            },
            body,
        )

    assert status == 200
    assert captured[0]["ARTEK_SSH_CONTROL_PATH"] == "/tmp/artek-test/%C"


def test_owner_exec_write_outside_home_does_not_run_subprocess(
    client_mod, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    proxy = _proxy(client_mod)
    called: list[int] = []
    monkeypatch.setattr(proxy.subprocess, "run", lambda *_a, **_k: called.append(1))
    dest = tmp_path.parent / f"artek-outside-{tmp_path.name}.patch"
    body = json.dumps({"command": f"git show --output={dest} HEAD", "cwd": "~"}).encode()
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
    assert status == 403
    _no_wildcard_cors(headers)
    assert called == []
    assert not dest.exists()


def test_read_thread_withdraws_only_that_bots_native_notification(
    client_mod, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    proxy = _proxy(client_mod)
    dismissed: list[str] = []
    monkeypatch.setattr(proxy, "_desktop_dismiss", lambda tag: dismissed.append(tag) or True)
    body = b'{"tag":"artek-buddy:bot-a"}'

    with running_proxy(client_mod, tmp_path, monkeypatch) as (httpd, port):
        origin = f"http://127.0.0.1:{port}"
        conn = HTTPConnection("127.0.0.1", port, timeout=5)
        try:
            conn.request(
                "POST",
                "/local/notify-dismiss",
                body=body,
                headers={
                    "Host": f"127.0.0.1:{port}",
                    "Origin": origin,
                    "Content-Type": "application/json",
                    "X-Artek-Local-Nonce": httpd.local_nonce,
                },
            )
            response = conn.getresponse()
            response.read()
        finally:
            conn.close()

    assert response.status == 200
    assert dismissed == ["artek-buddy:bot-a"]


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
            blank = HTTPConnection("127.0.0.1", port, timeout=5)
            blank.request("GET", "/local/status")
            missing = blank.getresponse()
            missing_body = json.loads(missing.read().decode("utf-8"))
            blank.close()
            cross = HTTPConnection("127.0.0.1", port, timeout=5)
            cross.request(
                "GET",
                "/local/status",
                headers={"Sec-Fetch-Site": "cross-site"},
            )
            crossed = cross.getresponse()
            crossed.read()
            cross.close()
        finally:
            ok.close()
            denied.close()
    assert good.status == 200
    assert payload["nonce"] == httpd.local_nonce
    assert payload["window_active"] is None
    assert bad.status == 403
    assert missing.status == 200
    assert missing_body["nonce"] == httpd.local_nonce
    assert crossed.status == 403


def test_local_unpair_forgets_the_device_token(
    client_mod, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    proxy = _proxy(client_mod)
    cfg = tmp_path / "artek-config"
    cfg.mkdir()
    token_path = cfg / "token"
    token_path.write_text("device-token", encoding="utf-8")
    monkeypatch.setattr(proxy, "_config_dir", lambda: cfg)
    with running_proxy(client_mod, tmp_path, monkeypatch) as (httpd, port):
        httpd.token = "device-token"
        origin = f"http://127.0.0.1:{port}"
        conn = HTTPConnection("127.0.0.1", port, timeout=5)
        try:
            conn.request("GET", "/local/status", headers={"Origin": origin})
            status = conn.getresponse()
            payload = json.loads(status.read().decode("utf-8"))
            nonce = payload["nonce"]
            conn.request(
                "POST",
                "/local/unpair",
                body=b"{}",
                headers={
                    "Host": f"127.0.0.1:{port}",
                    "Origin": origin,
                    "Content-Type": "application/json",
                    "X-Artek-Local-Nonce": nonce,
                },
            )
            gone = conn.getresponse()
            body = json.loads(gone.read().decode("utf-8"))
        finally:
            conn.close()
    assert gone.status == 200
    assert body["ok"] is True
    assert body["paired"] is False
    assert httpd.token == ""
    assert not token_path.exists()


def test_proxy_forwards_put_to_the_host(
    client_mod, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

    seen: list[tuple[str, bytes]] = []

    class Upstream(BaseHTTPRequestHandler):
        def do_PUT(self) -> None:
            length = int(self.headers.get("Content-Length") or 0)
            seen.append((self.path, self.rfile.read(length)))
            payload = b'{"ok":true}'
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, fmt: str, *args: object) -> None:
            return

    host = ThreadingHTTPServer(("127.0.0.1", 0), Upstream)
    host_thread = threading.Thread(target=host.serve_forever, daemon=True)
    host_thread.start()
    proxy = _proxy(client_mod)
    (tmp_path / "index.html").write_text("<!doctype html>", encoding="utf-8")
    monkeypatch.setattr(proxy, "web_root", lambda: tmp_path)
    httpd = None
    try:
        httpd = proxy.serve(f"http://127.0.0.1:{host.server_address[1]}", "dev_test", 0)
        loop = threading.Thread(target=httpd.serve_forever, daemon=True)
        loop.start()
        port = int(httpd.server_address[1])
        origin = f"http://127.0.0.1:{port}"
        conn = HTTPConnection("127.0.0.1", port, timeout=5)
        try:
            conn.request(
                "PUT",
                "/v1/bots/bot_deadbeefdeadbeef/credentials/github",
                body=b'{"secret":"fixture"}',
                headers={
                    "Host": f"127.0.0.1:{port}",
                    "Origin": origin,
                    "Content-Type": "application/json",
                },
            )
            resp = conn.getresponse()
            payload = resp.read()
        finally:
            conn.close()
    finally:
        if httpd is not None:
            httpd.shutdown()
            httpd.server_close()
        host.shutdown()
        host.server_close()
    assert resp.status == 200
    assert payload == b'{"ok":true}'
    assert seen == [
        ("/v1/bots/bot_deadbeefdeadbeef/credentials/github", b'{"secret":"fixture"}')
    ]
