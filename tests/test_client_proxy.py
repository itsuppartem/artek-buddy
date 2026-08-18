from __future__ import annotations

import importlib.util
import json
import os
import socket
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
CLIENT = ROOT / "client" / "artek_buddy.py"


def _load():
    spec = importlib.util.spec_from_file_location("artek_buddy_client", CLIENT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ClientProxyTest(unittest.TestCase):
    def test_token_prefers_user_config(self) -> None:
        module = _load()
        with tempfile.TemporaryDirectory() as raw:
            home = Path(raw)
            cfg = home / ".config" / "artek-buddy"
            cfg.mkdir(parents=True)
            (cfg / "token").write_text("user-device-token\n", encoding="utf-8")
            with patch.object(module.Path, "home", return_value=home):
                with patch.dict(os.environ, {"AGENT_HTTP_TOKEN": "env-token"}):
                    self.assertEqual(module._load_token(), "user-device-token")

    def test_token_ignores_host_env(self) -> None:
        module = _load()
        with tempfile.TemporaryDirectory() as raw:
            home = Path(raw)
            (home / ".config" / "artek-buddy").mkdir(parents=True)
            with patch.object(module.Path, "home", return_value=home):
                with patch.dict(os.environ, {"AGENT_HTTP_TOKEN": "env-token"}):
                    self.assertNotEqual(module._load_token(), "env-token")

    def test_local_status_unpaired(self) -> None:
        module = _load()
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            (root / "index.html").write_text("<div id='root'>Artek Buddy</div>\n", encoding="utf-8")
            module.WEB_ROOTS = (root,)
            httpd = module.serve("http://127.0.0.1:9", "", 0)
            thread = threading.Thread(target=httpd.serve_forever, daemon=True)
            thread.start()
            try:
                port = httpd.server_address[1]
                with urlopen(f"http://127.0.0.1:{port}/local/status", timeout=8) as resp:
                    payload = json.loads(resp.read().decode())
                self.assertFalse(payload["paired"])
                self.assertEqual(payload["url"], "http://127.0.0.1:9")
            finally:
                httpd.shutdown()
                httpd.server_close()

    def test_local_pair_writes_user_token(self) -> None:
        module = _load()

        class FakeHost(BaseHTTPRequestHandler):
            def log_message(self, fmt: str, *args) -> None:
                return

            def do_POST(self) -> None:
                length = int(self.headers.get("Content-Length") or 0)
                body = json.loads(self.rfile.read(length).decode()) if length else {}
                payload = {
                    "id": "dev_test",
                    "name": body.get("name"),
                    "platform": body.get("platform"),
                    "created_at": "2026-08-17T00:00:00Z",
                    "token": "dev_minted_once",
                }
                data = json.dumps(payload).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

        host = ThreadingHTTPServer(("127.0.0.1", 0), FakeHost)
        host_thread = threading.Thread(target=host.serve_forever, daemon=True)
        host_thread.start()
        with tempfile.TemporaryDirectory() as raw:
            home = Path(raw)
            root = home / "web"
            root.mkdir()
            (root / "index.html").write_text("<div id='root'>Artek Buddy</div>\n", encoding="utf-8")
            module.WEB_ROOTS = (root,)
            host_url = f"http://127.0.0.1:{host.server_address[1]}"
            httpd = module.serve(host_url, "", 0)
            thread = threading.Thread(target=httpd.serve_forever, daemon=True)
            thread.start()
            try:
                port = httpd.server_address[1]
                with patch.object(module.Path, "home", return_value=home):
                    req = Request(
                        f"http://127.0.0.1:{port}/local/pair",
                        data=json.dumps(
                            {"pairing_code": "ABCD-EFGH", "name": "desktop", "platform": "linux"}
                        ).encode(),
                        headers={"Content-Type": "application/json"},
                        method="POST",
                    )
                    with urlopen(req, timeout=8) as resp:
                        payload = json.loads(resp.read().decode())
                self.assertTrue(payload["ok"])
                self.assertEqual(payload["device"]["id"], "dev_test")
                self.assertNotIn("token", payload)
                self.assertNotIn("token", payload.get("device") or {})
                token_path = home / ".config" / "artek-buddy" / "token"
                self.assertEqual(token_path.read_text(encoding="utf-8").strip(), "dev_minted_once")
                self.assertEqual(token_path.stat().st_mode & 0o777, 0o600)
                self.assertEqual(httpd.token, "dev_minted_once")
                with urlopen(f"http://127.0.0.1:{port}/local/status", timeout=8) as resp:
                    status = json.loads(resp.read().decode())
                self.assertTrue(status["paired"])
            finally:
                httpd.shutdown()
                httpd.server_close()
                host.shutdown()
                host.server_close()

    def test_local_pair_rejects_bad_code(self) -> None:
        module = _load()

        class FakeHost(BaseHTTPRequestHandler):
            def log_message(self, fmt: str, *args) -> None:
                return

            def do_POST(self) -> None:
                data = json.dumps({"detail": "invalid or expired pairing code"}).encode()
                self.send_response(403)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

        host = ThreadingHTTPServer(("127.0.0.1", 0), FakeHost)
        host_thread = threading.Thread(target=host.serve_forever, daemon=True)
        host_thread.start()
        with tempfile.TemporaryDirectory() as raw:
            home = Path(raw)
            root = home / "web"
            root.mkdir()
            (root / "index.html").write_text("<div id='root'>Artek Buddy</div>\n", encoding="utf-8")
            module.WEB_ROOTS = (root,)
            httpd = module.serve(f"http://127.0.0.1:{host.server_address[1]}", "", 0)
            thread = threading.Thread(target=httpd.serve_forever, daemon=True)
            thread.start()
            try:
                port = httpd.server_address[1]
                req = Request(
                    f"http://127.0.0.1:{port}/local/pair",
                    data=json.dumps({"pairing_code": "ZZZZ-ZZZZ", "name": "desktop"}).encode(),
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                with self.assertRaises(HTTPError) as raised:
                    urlopen(req, timeout=8)
                self.assertEqual(raised.exception.code, 403)
                self.assertFalse((home / ".config" / "artek-buddy" / "token").exists())
            finally:
                httpd.shutdown()
                httpd.server_close()
                host.shutdown()
                host.server_close()

    def test_local_notify_loopback(self) -> None:
        module = _load()
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            (root / "index.html").write_text("<div id='root'>Artek Buddy</div>\n", encoding="utf-8")
            module.WEB_ROOTS = (root,)
            httpd = module.serve("http://127.0.0.1:9", "", 0)
            thread = threading.Thread(target=httpd.serve_forever, daemon=True)
            thread.start()
            try:
                port = httpd.server_address[1]
                with patch.object(module, "_desktop_notify") as notify:
                    req = Request(
                        f"http://127.0.0.1:{port}/local/notify",
                        data=json.dumps(
                            {"title": "Weather replied", "body": "24C", "urgency": "normal"}
                        ).encode(),
                        headers={"Content-Type": "application/json"},
                        method="POST",
                    )
                    with urlopen(req, timeout=8) as resp:
                        payload = json.loads(resp.read().decode())
                self.assertTrue(payload["ok"])
                notify.assert_called_once_with("Weather replied", "24C", "normal")
            finally:
                httpd.shutdown()
                httpd.server_close()

    def test_local_notify_rejects_bad_json(self) -> None:
        module = _load()
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            (root / "index.html").write_text("<div id='root'>Artek Buddy</div>\n", encoding="utf-8")
            module.WEB_ROOTS = (root,)
            httpd = module.serve("http://127.0.0.1:9", "", 0)
            thread = threading.Thread(target=httpd.serve_forever, daemon=True)
            thread.start()
            try:
                port = httpd.server_address[1]
                req = Request(
                    f"http://127.0.0.1:{port}/local/notify",
                    data=b"{not-json",
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                with self.assertRaises(HTTPError) as raised:
                    urlopen(req, timeout=8)
                self.assertEqual(raised.exception.code, 400)
            finally:
                httpd.shutdown()
                httpd.server_close()

    def test_desktop_notify_uses_argv(self) -> None:
        module = _load()
        with patch.dict(os.environ, {"ARTEK_BUDDY_NOTIFY": "1"}, clear=False):
            with patch.object(module.shutil, "which", return_value="/usr/bin/notify-send"):
                with patch.object(module.subprocess, "run") as run:
                    with patch.object(module, "_apply_urgency"):
                        module._desktop_notify("Hello", "World", "critical")
        run.assert_called_once()
        args = run.call_args[0][0]
        self.assertEqual(args[0], "/usr/bin/notify-send")
        self.assertIn("--app-name=Artek Buddy", args)
        self.assertEqual(args[-3:], ["--", "Hello", "World"])

    def test_desktop_notify_can_be_disabled(self) -> None:
        module = _load()
        with patch.dict(os.environ, {"ARTEK_BUDDY_NOTIFY": "0"}, clear=False):
            with patch.object(module.subprocess, "run") as run:
                with patch.object(module, "_apply_urgency"):
                    module._desktop_notify("Hello", "World", "normal")
        run.assert_not_called()

    def test_proxy_has_patch_and_delete(self) -> None:
        module = _load()
        self.assertTrue(hasattr(module.Handler, "do_PATCH"))
        self.assertTrue(hasattr(module.Handler, "do_DELETE"))
        self.assertTrue(hasattr(module.Handler, "_proxy_ws"))

    def test_novnc_http_is_proxied(self) -> None:
        module = _load()

        class FakeHost(BaseHTTPRequestHandler):
            def log_message(self, fmt: str, *args) -> None:
                return

            def do_GET(self) -> None:
                data = b"novnc-ok"
                self.send_response(200)
                self.send_header("Content-Type", "text/plain")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

        host = ThreadingHTTPServer(("127.0.0.1", 0), FakeHost)
        thread = threading.Thread(target=host.serve_forever, daemon=True)
        thread.start()
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            (root / "index.html").write_text("<div id='root'>Artek Buddy</div>\n", encoding="utf-8")
            module.WEB_ROOTS = (root,)
            httpd = module.serve(f"http://127.0.0.1:{host.server_address[1]}", "dev-token", 0)
            proxy_thread = threading.Thread(target=httpd.serve_forever, daemon=True)
            proxy_thread.start()
            try:
                port = httpd.server_address[1]
                with urlopen(f"http://127.0.0.1:{port}/novnc/signed/embed.html", timeout=8) as resp:
                    self.assertEqual(resp.read(), b"novnc-ok")
            finally:
                httpd.shutdown()
                httpd.server_close()
                host.shutdown()
                host.server_close()

    def test_novnc_ws_upgrade_is_http11(self) -> None:
        module = _load()

        class FakeHost(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, fmt: str, *args) -> None:
                return

            def do_GET(self) -> None:
                self.send_response(101, "Switching Protocols")
                self.send_header("Upgrade", "websocket")
                self.send_header("Connection", "Upgrade")
                self.send_header("Sec-WebSocket-Accept", "s3pPLMBiTxaQ9kYGzzhZRbK+xOo=")
                self.end_headers()

        host = ThreadingHTTPServer(("127.0.0.1", 0), FakeHost)
        thread = threading.Thread(target=host.serve_forever, daemon=True)
        thread.start()
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            (root / "index.html").write_text("<div id='root'>Artek Buddy</div>\n", encoding="utf-8")
            module.WEB_ROOTS = (root,)
            httpd = module.serve(f"http://127.0.0.1:{host.server_address[1]}", "dev-token", 0)
            proxy_thread = threading.Thread(target=httpd.serve_forever, daemon=True)
            proxy_thread.start()
            raw_sock = None
            try:
                port = httpd.server_address[1]
                raw_sock = socket.create_connection(("127.0.0.1", port), timeout=5)
                raw_sock.sendall(
                    b"GET /novnc/signed/websockify HTTP/1.1\r\n"
                    b"Host: 127.0.0.1\r\n"
                    b"Upgrade: websocket\r\n"
                    b"Connection: Upgrade\r\n"
                    b"Sec-WebSocket-Key: dGhlIHNhbXBsZSBub25jZQ==\r\n"
                    b"Sec-WebSocket-Version: 13\r\n\r\n"
                )
                resp = raw_sock.recv(512)
                self.assertTrue(resp.startswith(b"HTTP/1.1 101"), resp[:80])
            finally:
                if raw_sock is not None:
                    raw_sock.close()
                httpd.shutdown()
                httpd.server_close()
                host.shutdown()
                host.server_close()

    def test_serves_the_shell_without_the_live_host(self) -> None:
        module = _load()
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            (root / "index.html").write_text("<div id='root'>Artek Buddy</div>\n", encoding="utf-8")
            module.WEB_ROOTS = (root,)
            httpd = module.serve("http://127.0.0.1:9", "test-token", 0)
            thread = threading.Thread(target=httpd.serve_forever, daemon=True)
            thread.start()
            try:
                port = httpd.server_address[1]
                with urlopen(f"http://127.0.0.1:{port}/", timeout=8) as resp:
                    html = resp.read().decode()
                self.assertIn("root", html)
            finally:
                httpd.shutdown()
                httpd.server_close()

    def test_local_unpair_forgets_the_device_token(self) -> None:
        module = _load()
        with tempfile.TemporaryDirectory() as raw:
            home = Path(raw)
            cfg = home / ".config" / "artek-buddy"
            cfg.mkdir(parents=True)
            (cfg / "token").write_text("dev_forget_me\n", encoding="utf-8")
            root = home / "web"
            root.mkdir()
            (root / "index.html").write_text("<div id='root'>Artek Buddy</div>\n", encoding="utf-8")
            module.WEB_ROOTS = (root,)
            httpd = module.serve("http://127.0.0.1:9", "dev_forget_me", 0)
            thread = threading.Thread(target=httpd.serve_forever, daemon=True)
            thread.start()
            try:
                port = httpd.server_address[1]
                with patch.object(module.Path, "home", return_value=home):
                    req = Request(
                        f"http://127.0.0.1:{port}/local/unpair",
                        data=b"{}",
                        headers={"Content-Type": "application/json"},
                        method="POST",
                    )
                    with urlopen(req, timeout=8) as resp:
                        payload = json.loads(resp.read().decode())
                    self.assertTrue(payload["ok"])
                    self.assertFalse(payload["paired"])
                    self.assertFalse((cfg / "token").exists())
                    self.assertEqual(httpd.token, "")
                    with urlopen(f"http://127.0.0.1:{port}/local/status", timeout=8) as resp:
                        status = json.loads(resp.read().decode())
                    self.assertFalse(status["paired"])
            finally:
                httpd.shutdown()
                httpd.server_close()

    def test_proxy_health_when_host_is_up(self) -> None:
        token_path = ROOT / "client" / "token"
        if not token_path.is_file():
            self.skipTest("local token missing")
        try:
            with urlopen("http://127.0.0.1:8080/health", timeout=2) as resp:
                if resp.status != 200:
                    self.skipTest("host not healthy")
        except OSError:
            self.skipTest("host not reachable")
        if not (ROOT / "client" / "web" / "dist" / "index.html").is_file():
            self.skipTest("web UI not built")
        module = _load()
        token = token_path.read_text().strip()
        httpd = module.serve("http://127.0.0.1:8080", token, 0)
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        try:
            port = httpd.server_address[1]
            with urlopen(f"http://127.0.0.1:{port}/health", timeout=8) as resp:
                payload = json.loads(resp.read().decode())
            self.assertTrue(payload.get("ok"))
            with urlopen(f"http://127.0.0.1:{port}/v1/bots", timeout=8) as resp:
                bots = json.loads(resp.read().decode())
            self.assertIn("bots", bots)
        finally:
            httpd.shutdown()
            httpd.server_close()

    def test_pairing_url_allowlist(self) -> None:
        module = _load()
        self.assertTrue(module.pairing_url_allowed("http://127.0.0.1:8080"))
        self.assertTrue(module.pairing_url_allowed("http://192.168.1.10:8080"))
        self.assertTrue(module.pairing_url_allowed("http://100.64.1.2:8080"))
        self.assertTrue(module.pairing_url_allowed("https://pi.ts.net"))
        self.assertFalse(module.pairing_url_allowed("https://example.com"))
        self.assertFalse(module.pairing_url_allowed("ftp://127.0.0.1"))

    def test_proxy_origin_allowlist(self) -> None:
        module = _load()
        self.assertTrue(module.proxy_origin_allowed(None, None, 4173))
        self.assertTrue(module.proxy_origin_allowed("http://127.0.0.1:4173", "same-origin", 4173))
        self.assertFalse(module.proxy_origin_allowed("https://evil.example", "cross-site", 4173))
        self.assertFalse(module.proxy_origin_allowed("http://127.0.0.1:9999", None, 4173))

    def test_redacts_novnc_paths_in_logs(self) -> None:
        module = _load()
        raw = 'GET /novnc/view/127.0.0.1/6080/embed.html?sig=secret HTTP/1.1" 200 -'
        self.assertEqual(module._redact_client_log(raw), 'GET /novnc/[redacted] HTTP/1.1" 200 -')

    def test_proxy_rejects_cross_site(self) -> None:
        module = _load()
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            (root / "index.html").write_text("<div id='root'>Artek Buddy</div>\n", encoding="utf-8")
            module.WEB_ROOTS = (root,)
            httpd = module.serve("http://127.0.0.1:9", "dev-token", 0)
            thread = threading.Thread(target=httpd.serve_forever, daemon=True)
            thread.start()
            try:
                port = httpd.server_address[1]
                req = Request(
                    f"http://127.0.0.1:{port}/health",
                    headers={
                        "Origin": "https://evil.example",
                        "Sec-Fetch-Site": "cross-site",
                    },
                )
                with self.assertRaises(HTTPError) as raised:
                    urlopen(req, timeout=8)
                self.assertEqual(raised.exception.code, 403)
            finally:
                httpd.shutdown()
                httpd.server_close()

    def test_local_pair_rejects_public_url(self) -> None:
        module = _load()
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            (root / "index.html").write_text("<div id='root'>Artek Buddy</div>\n", encoding="utf-8")
            module.WEB_ROOTS = (root,)
            httpd = module.serve("http://127.0.0.1:9", "", 0)
            thread = threading.Thread(target=httpd.serve_forever, daemon=True)
            thread.start()
            try:
                port = httpd.server_address[1]
                req = Request(
                    f"http://127.0.0.1:{port}/local/pair",
                    data=json.dumps(
                        {
                            "pairing_code": "ABCD-EFGH",
                            "name": "desktop",
                            "url": "https://example.com",
                        }
                    ).encode(),
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                with self.assertRaises(HTTPError) as raised:
                    urlopen(req, timeout=8)
                self.assertEqual(raised.exception.code, 400)
            finally:
                httpd.shutdown()
                httpd.server_close()
