from __future__ import annotations

import base64
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

    def test_local_owner_read_under_home(self) -> None:
        module = _load()
        with tempfile.TemporaryDirectory() as raw:
            home = Path(raw)
            notes = home / "notes.txt"
            notes.write_text("hello from the owner pc\n", encoding="utf-8")
            root = home / "web"
            root.mkdir()
            (root / "index.html").write_text("<div id='root'>Artek Buddy</div>\n", encoding="utf-8")
            module.WEB_ROOTS = (root,)
            httpd = module.serve("http://127.0.0.1:9", "", 0)
            thread = threading.Thread(target=httpd.serve_forever, daemon=True)
            thread.start()
            try:
                port = httpd.server_address[1]
                with patch.object(module.Path, "home", return_value=home):
                    req = Request(
                        f"http://127.0.0.1:{port}/local/owner-read",
                        data=json.dumps({"path": str(notes)}).encode(),
                        headers={"Content-Type": "application/json"},
                        method="POST",
                    )
                    with urlopen(req, timeout=8) as resp:
                        payload = json.loads(resp.read().decode())
                self.assertTrue(payload["ok"])
                self.assertEqual(payload["name"], "notes.txt")
                self.assertIn("hello from the owner pc", payload["text"])
            finally:
                httpd.shutdown()
                httpd.server_close()

    def test_local_owner_read_rejects_outside_home(self) -> None:
        module = _load()
        with tempfile.TemporaryDirectory() as raw:
            home = Path(raw) / "home"
            home.mkdir()
            outside = Path(raw) / "secret.txt"
            outside.write_text("nope\n", encoding="utf-8")
            root = home / "web"
            root.mkdir()
            (root / "index.html").write_text("<div id='root'>Artek Buddy</div>\n", encoding="utf-8")
            module.WEB_ROOTS = (root,)
            httpd = module.serve("http://127.0.0.1:9", "", 0)
            thread = threading.Thread(target=httpd.serve_forever, daemon=True)
            thread.start()
            try:
                port = httpd.server_address[1]
                with patch.object(module.Path, "home", return_value=home):
                    req = Request(
                        f"http://127.0.0.1:{port}/local/owner-read",
                        data=json.dumps({"path": str(outside)}).encode(),
                        headers={"Content-Type": "application/json"},
                        method="POST",
                    )
                    try:
                        urlopen(req, timeout=8)
                        self.fail("expected HTTPError")
                    except HTTPError as err:
                        self.assertEqual(err.code, 403)
            finally:
                httpd.shutdown()
                httpd.server_close()

    def test_local_owner_write_and_exec(self) -> None:
        module = _load()
        with tempfile.TemporaryDirectory() as raw:
            home = Path(raw)
            root = home / "web"
            root.mkdir()
            (root / "index.html").write_text("<div id='root'>Artek Buddy</div>\n", encoding="utf-8")
            module.WEB_ROOTS = (root,)
            httpd = module.serve("http://127.0.0.1:9", "", 0)
            thread = threading.Thread(target=httpd.serve_forever, daemon=True)
            thread.start()
            try:
                port = httpd.server_address[1]
                with patch.object(module.Path, "home", return_value=home):
                    write_req = Request(
                        f"http://127.0.0.1:{port}/local/owner-write",
                        data=json.dumps({"path": str(home / "hello.txt"), "text": "hi\n"}).encode(),
                        headers={"Content-Type": "application/json"},
                        method="POST",
                    )
                    with urlopen(write_req, timeout=8) as resp:
                        written = json.loads(resp.read().decode())
                    self.assertTrue(written["ok"])
                    self.assertEqual((home / "hello.txt").read_text(encoding="utf-8"), "hi\n")
                    list_req = Request(
                        f"http://127.0.0.1:{port}/local/owner-list",
                        data=json.dumps({"path": "~"}).encode(),
                        headers={"Content-Type": "application/json"},
                        method="POST",
                    )
                    with urlopen(list_req, timeout=8) as resp:
                        listed = json.loads(resp.read().decode())
                    self.assertTrue(listed["ok"])
                    self.assertTrue(any(item["name"] == "hello.txt" for item in listed["entries"]))
                    exec_req = Request(
                        f"http://127.0.0.1:{port}/local/owner-exec",
                        data=json.dumps({"command": "echo ssh-like", "cwd": "~"}).encode(),
                        headers={"Content-Type": "application/json"},
                        method="POST",
                    )
                    with urlopen(exec_req, timeout=8) as resp:
                        ran = json.loads(resp.read().decode())
                    self.assertTrue(ran["ok"])
                    self.assertIn("ssh-like", ran["stdout"])
                    self.assertEqual(ran["exit_code"], 0)
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

    def test_local_save_artifact_writes_downloads(self) -> None:
        module = _load()

        class FakeHost(BaseHTTPRequestHandler):
            def log_message(self, fmt: str, *args) -> None:
                return

            def do_GET(self) -> None:
                if self.path != "/v1/artifacts/art_1":
                    self.send_error(404)
                    return
                data = b"hello from the bot"
                self.send_response(200)
                self.send_header("Content-Type", "text/plain")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

        host = ThreadingHTTPServer(("127.0.0.1", 0), FakeHost)
        thread = threading.Thread(target=host.serve_forever, daemon=True)
        thread.start()
        with tempfile.TemporaryDirectory() as raw:
            home = Path(raw)
            root = home / "web"
            root.mkdir()
            (root / "index.html").write_text("<div id='root'>Artek Buddy</div>\n", encoding="utf-8")
            module.WEB_ROOTS = (root,)
            httpd = module.serve(f"http://127.0.0.1:{host.server_address[1]}", "dev-token", 0)
            proxy = threading.Thread(target=httpd.serve_forever, daemon=True)
            proxy.start()
            try:
                port = httpd.server_address[1]
                with patch.object(module.Path, "home", return_value=home):
                    req = Request(
                        f"http://127.0.0.1:{port}/local/save-artifact",
                        data=json.dumps({"artifact_id": "art_1", "name": "notes.txt"}).encode(),
                        headers={"Content-Type": "application/json"},
                        method="POST",
                    )
                    with urlopen(req, timeout=8) as resp:
                        payload = json.loads(resp.read().decode())
                self.assertTrue(payload["ok"])
                saved = home / "Downloads" / "notes.txt"
                self.assertEqual(saved.read_text(encoding="utf-8"), "hello from the bot")
            finally:
                httpd.shutdown()
                httpd.server_close()
                host.shutdown()
                host.server_close()

    def test_local_save_home_file_writes_downloads(self) -> None:
        module = _load()

        class FakeHost(BaseHTTPRequestHandler):
            def log_message(self, fmt: str, *args) -> None:
                return

            def do_GET(self) -> None:
                if not self.path.startswith("/v1/computer/bot_abc/files/raw"):
                    self.send_error(404)
                    return
                data = b"from the sandbox"
                self.send_response(200)
                self.send_header("Content-Type", "text/plain")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

        host = ThreadingHTTPServer(("127.0.0.1", 0), FakeHost)
        thread = threading.Thread(target=host.serve_forever, daemon=True)
        thread.start()
        with tempfile.TemporaryDirectory() as raw:
            home = Path(raw)
            root = home / "web"
            root.mkdir()
            (root / "index.html").write_text("<div id='root'>Artek Buddy</div>\n", encoding="utf-8")
            module.WEB_ROOTS = (root,)
            httpd = module.serve(f"http://127.0.0.1:{host.server_address[1]}", "dev-token", 0)
            proxy = threading.Thread(target=httpd.serve_forever, daemon=True)
            proxy.start()
            try:
                port = httpd.server_address[1]
                with patch.object(module.Path, "home", return_value=home):
                    req = Request(
                        f"http://127.0.0.1:{port}/local/save-home-file",
                        data=json.dumps(
                            {"bot_id": "bot_abc", "path": "inbox/notes.txt", "name": "notes.txt"}
                        ).encode(),
                        headers={"Content-Type": "application/json"},
                        method="POST",
                    )
                    with urlopen(req, timeout=8) as resp:
                        payload = json.loads(resp.read().decode())
                self.assertTrue(payload["ok"])
                saved = home / "Downloads" / "notes.txt"
                self.assertEqual(saved.read_text(encoding="utf-8"), "from the sandbox")
            finally:
                httpd.shutdown()
                httpd.server_close()
                host.shutdown()
                host.server_close()

    def test_local_save_home_file_rejects_escape_and_missing(self) -> None:
        module = _load()

        class FakeHost(BaseHTTPRequestHandler):
            def log_message(self, fmt: str, *args) -> None:
                return

            def do_GET(self) -> None:
                self.send_error(404)

        host = ThreadingHTTPServer(("127.0.0.1", 0), FakeHost)
        thread = threading.Thread(target=host.serve_forever, daemon=True)
        thread.start()
        with tempfile.TemporaryDirectory() as raw:
            home = Path(raw)
            root = home / "web"
            root.mkdir()
            (root / "index.html").write_text("<div id='root'>Artek Buddy</div>\n", encoding="utf-8")
            module.WEB_ROOTS = (root,)
            httpd = module.serve(f"http://127.0.0.1:{host.server_address[1]}", "dev-token", 0)
            proxy = threading.Thread(target=httpd.serve_forever, daemon=True)
            proxy.start()
            try:
                port = httpd.server_address[1]
                with patch.object(module.Path, "home", return_value=home):
                    escape = Request(
                        f"http://127.0.0.1:{port}/local/save-home-file",
                        data=json.dumps(
                            {"bot_id": "bot_abc", "path": "../etc/passwd", "name": "passwd"}
                        ).encode(),
                        headers={"Content-Type": "application/json"},
                        method="POST",
                    )
                    with self.assertRaises(HTTPError) as err:
                        urlopen(escape, timeout=8)
                    self.assertEqual(err.exception.code, 400)
                    missing = Request(
                        f"http://127.0.0.1:{port}/local/save-home-file",
                        data=json.dumps(
                            {"bot_id": "bot_abc", "path": "inbox/gone.txt", "name": "gone.txt"}
                        ).encode(),
                        headers={"Content-Type": "application/json"},
                        method="POST",
                    )
                    with self.assertRaises(HTTPError) as gone:
                        urlopen(missing, timeout=8)
                    self.assertIn(gone.exception.code, {404, 502})
                downloads = home / "Downloads"
                if downloads.exists():
                    self.assertEqual(list(downloads.iterdir()), [])
            finally:
                httpd.shutdown()
                httpd.server_close()
                host.shutdown()
                host.server_close()

    def test_local_save_artifact_uses_russian_downloads_and_does_not_overwrite(self) -> None:
        module = _load()

        class FakeHost(BaseHTTPRequestHandler):
            def log_message(self, fmt: str, *args) -> None:
                return

            def do_GET(self) -> None:
                if self.path != "/v1/artifacts/art_1":
                    self.send_error(404)
                    return
                data = b"second copy"
                self.send_response(200)
                self.send_header("Content-Type", "text/plain")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

        host = ThreadingHTTPServer(("127.0.0.1", 0), FakeHost)
        thread = threading.Thread(target=host.serve_forever, daemon=True)
        thread.start()
        with tempfile.TemporaryDirectory() as raw:
            home = Path(raw)
            (home / "Загрузки").mkdir()
            (home / "Загрузки" / "notes.txt").write_text("keep me", encoding="utf-8")
            root = home / "web"
            root.mkdir()
            (root / "index.html").write_text("<div id='root'>Artek Buddy</div>\n", encoding="utf-8")
            module.WEB_ROOTS = (root,)
            httpd = module.serve(f"http://127.0.0.1:{host.server_address[1]}", "dev-token", 0)
            proxy = threading.Thread(target=httpd.serve_forever, daemon=True)
            proxy.start()
            try:
                port = httpd.server_address[1]
                with patch.object(module.Path, "home", return_value=home):
                    req = Request(
                        f"http://127.0.0.1:{port}/local/save-artifact",
                        data=json.dumps({"artifact_id": "art_1", "name": "notes.txt"}).encode(),
                        headers={"Content-Type": "application/json"},
                        method="POST",
                    )
                    with urlopen(req, timeout=8) as resp:
                        payload = json.loads(resp.read().decode())
                self.assertTrue(payload["ok"])
                self.assertEqual((home / "Загрузки" / "notes.txt").read_text(encoding="utf-8"), "keep me")
                self.assertEqual((home / "Загрузки" / "notes-2.txt").read_text(encoding="utf-8"), "second copy")
                self.assertFalse((home / "Downloads").exists())
            finally:
                httpd.shutdown()
                httpd.server_close()
                host.shutdown()
                host.server_close()

    def test_choose_save_path_uses_hook_or_downloads_without_a_window(self) -> None:
        module = _load()
        with tempfile.TemporaryDirectory() as raw:
            home = Path(raw)
            dest = home / "picked" / "kotik.png"
            module.save_path_chooser = lambda name: dest
            self.assertEqual(module.choose_save_path("kotik.png"), dest)
            module.save_path_chooser = lambda name: None
            self.assertIsNone(module.choose_save_path("kotik.png"))
            module.save_path_chooser = None
            with patch.object(module.Path, "home", return_value=home):
                self.assertEqual(module.choose_save_path("kotik.png"), home / "Downloads" / "kotik.png")
            with patch.dict(os.environ, {"ARTEK_SAVE_NO_DIALOG": "1"}):
                module._GTK_WINDOWS.append(object())
                try:
                    with patch.object(module.Path, "home", return_value=home):
                        self.assertEqual(
                            module.choose_save_path("other.png"),
                            home / "Downloads" / "other.png",
                        )
                finally:
                    module._GTK_WINDOWS.clear()

    def test_local_save_artifact_writes_chosen_path_and_honors_cancel(self) -> None:
        module = _load()

        class FakeHost(BaseHTTPRequestHandler):
            def log_message(self, fmt: str, *args) -> None:
                return

            def do_GET(self) -> None:
                if self.path != "/v1/artifacts/art_1":
                    self.send_error(404)
                    return
                data = b"chosen bytes"
                self.send_response(200)
                self.send_header("Content-Type", "image/png")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

        host = ThreadingHTTPServer(("127.0.0.1", 0), FakeHost)
        thread = threading.Thread(target=host.serve_forever, daemon=True)
        thread.start()
        with tempfile.TemporaryDirectory() as raw:
            home = Path(raw)
            picked = home / "Desktop" / "kotik.png"
            root = home / "web"
            root.mkdir()
            (root / "index.html").write_text("<div id='root'>Artek Buddy</div>\n", encoding="utf-8")
            module.WEB_ROOTS = (root,)
            httpd = module.serve(f"http://127.0.0.1:{host.server_address[1]}", "dev-token", 0)
            proxy = threading.Thread(target=httpd.serve_forever, daemon=True)
            proxy.start()
            try:
                port = httpd.server_address[1]
                module.save_path_chooser = lambda name: picked
                with patch.object(module.Path, "home", return_value=home):
                    req = Request(
                        f"http://127.0.0.1:{port}/local/save-artifact",
                        data=json.dumps({"artifact_id": "art_1", "name": "kotik.png"}).encode(),
                        headers={"Content-Type": "application/json"},
                        method="POST",
                    )
                    with urlopen(req, timeout=8) as resp:
                        payload = json.loads(resp.read().decode())
                self.assertTrue(payload["ok"])
                self.assertEqual(payload["path"], str(picked))
                self.assertEqual(picked.read_bytes(), b"chosen bytes")
                self.assertFalse((home / "Downloads").exists())

                module.save_path_chooser = lambda name: None
                cancel = Request(
                    f"http://127.0.0.1:{port}/local/save-artifact",
                    data=json.dumps({"artifact_id": "art_1", "name": "kotik.png"}).encode(),
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                with self.assertRaises(HTTPError) as err:
                    urlopen(cancel, timeout=8)
                self.assertEqual(err.exception.code, 409)
                body = json.loads(err.exception.read().decode())
                self.assertTrue(body.get("cancelled"))
                self.assertEqual(picked.read_bytes(), b"chosen bytes")
            finally:
                module.save_path_chooser = None
                httpd.shutdown()
                httpd.server_close()
                host.shutdown()
                host.server_close()

    def test_owner_path_maps_downloads_and_says_missing(self) -> None:
        module = _load()
        with tempfile.TemporaryDirectory() as raw:
            home = Path(raw)
            (home / "Загрузки").mkdir()
            (home / "Загрузки" / "shot.png").write_bytes(b"x")
            found, err = module.inspect_owner_path("~/Downloads", home, as_dir=True)
            self.assertEqual(err, "")
            self.assertEqual(found, (home / "Загрузки").resolve())
            missing, why = module.inspect_owner_path("~/no-such-dir", home, as_dir=True)
            self.assertIsNone(missing)
            self.assertEqual(why, "folder not found")
            outside, jail = module.inspect_owner_path("/etc/passwd", home, must_exist=False)
            self.assertIsNone(outside)
            self.assertIn("outside", jail)

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

    def test_local_attach_files_reads_home_file(self) -> None:
        module = _load()
        with tempfile.TemporaryDirectory() as raw:
            home = Path(raw)
            pictures = home / "Изображения" / "Снимки экрана"
            pictures.mkdir(parents=True)
            shot = pictures / "edbc3632c9584b229513834046b1ab84.jpeg"
            shot.write_bytes(b"\xff\xd8\xff jpeg-bytes")
            root = home / "web"
            root.mkdir()
            (root / "index.html").write_text("<div id='root'>Artek Buddy</div>\n", encoding="utf-8")
            module.WEB_ROOTS = (root,)
            httpd = module.serve("http://127.0.0.1:9", "", 0)
            thread = threading.Thread(target=httpd.serve_forever, daemon=True)
            thread.start()
            try:
                port = httpd.server_address[1]
                with patch.object(module.Path, "home", return_value=home):
                    req = Request(
                        f"http://127.0.0.1:{port}/local/attach-files",
                        data=json.dumps({"paths": [str(shot)]}).encode(),
                        headers={"Content-Type": "application/json"},
                        method="POST",
                    )
                    with urlopen(req, timeout=8) as resp:
                        payload = json.loads(resp.read().decode())
                self.assertTrue(payload["ok"])
                self.assertEqual(payload["files"][0]["name"], shot.name)
                self.assertEqual(payload["files"][0]["type"], "image/jpeg")
                self.assertEqual(
                    base64.b64decode(payload["files"][0]["content_base64"]),
                    b"\xff\xd8\xff jpeg-bytes",
                )
            finally:
                httpd.shutdown()
                httpd.server_close()

    def test_local_attach_files_rejects_outside_home(self) -> None:
        module = _load()
        with tempfile.TemporaryDirectory() as raw:
            home = Path(raw) / "home"
            home.mkdir()
            outside = Path(raw) / "secret.bin"
            outside.write_bytes(b"nope")
            root = home / "web"
            root.mkdir()
            (root / "index.html").write_text("<div id='root'>Artek Buddy</div>\n", encoding="utf-8")
            module.WEB_ROOTS = (root,)
            httpd = module.serve("http://127.0.0.1:9", "", 0)
            thread = threading.Thread(target=httpd.serve_forever, daemon=True)
            thread.start()
            try:
                port = httpd.server_address[1]
                with patch.object(module.Path, "home", return_value=home):
                    req = Request(
                        f"http://127.0.0.1:{port}/local/attach-files",
                        data=json.dumps({"paths": [str(outside)]}).encode(),
                        headers={"Content-Type": "application/json"},
                        method="POST",
                    )
                    try:
                        urlopen(req, timeout=8)
                        self.fail("expected HTTPError")
                    except HTTPError as err:
                        self.assertEqual(err.code, 403)
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
