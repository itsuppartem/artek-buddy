#!/usr/bin/env python3
"""Desktop shell: local proxy + web UI. Credentials stay on this machine."""

from __future__ import annotations

import argparse
import http.client
import json
import mimetypes
import os
import select
import shutil
import socket
import ssl
import subprocess
import sys
import threading
import traceback
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

WEB_ROOTS = (
    Path("/usr/lib/artek-buddy-client/web"),
    Path(__file__).with_name("web") / "dist",
)
_WINDOW_LOCK = threading.Lock()
_GTK_WINDOWS: list[object] = []


def _log(message: str) -> None:
    try:
        path = Path.home() / ".config" / "artek-buddy" / "client.log"
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(message.rstrip() + "\n")
    except OSError:
        pass
    sys.stderr.write(message.rstrip() + "\n")


def _config_dir() -> Path:
    return Path.home() / ".config" / "artek-buddy"


def _load_url() -> str:
    candidates = [
        _config_dir() / "url",
        Path("/usr/lib/artek-buddy-client/url"),
        Path(__file__).with_name("url"),
    ]
    for path in candidates:
        try:
            value = path.read_text(encoding="utf-8").strip()
        except OSError:
            continue
        if value:
            return value.rstrip("/")
    return os.environ.get("ARTEK_BUDDY_URL", "http://127.0.0.1:8080").rstrip("/")


def _load_token() -> str:
    if os.environ.get("ARTEK_BUDDY_UNPAIRED") == "1":
        return ""
    try:
        value = (_config_dir() / "token").read_text(encoding="utf-8").strip()
    except OSError:
        value = ""
    if value:
        return value
    env = os.environ.get("AGENT_HTTP_TOKEN", "").strip()
    if env:
        return env
    for path in (
        Path("/usr/lib/artek-buddy-client/token"),
        Path(__file__).with_name("token"),
    ):
        try:
            leftover = path.read_text(encoding="utf-8").strip()
        except OSError:
            continue
        if leftover:
            return leftover
    return ""


def _write_text(path: Path, value: str, mode: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value.strip() + "\n", encoding="utf-8")
    path.chmod(mode)


def _host_request(url: str, method: str, path: str, body: bytes, headers: dict[str, str]) -> tuple[int, bytes]:
    upstream = urlsplit(url)
    if upstream.scheme == "https":
        conn: http.client.HTTPConnection = http.client.HTTPSConnection(
            upstream.hostname or "127.0.0.1",
            upstream.port or 443,
            timeout=30,
            context=ssl.create_default_context(),
        )
    else:
        conn = http.client.HTTPConnection(
            upstream.hostname or "127.0.0.1",
            upstream.port or 80,
            timeout=30,
        )
    try:
        conn.request(method, path, body=body or None, headers=headers)
        resp = conn.getresponse()
        return resp.status, resp.read()
    finally:
        conn.close()


def web_root() -> Path:
    for path in WEB_ROOTS:
        if (path / "index.html").is_file():
            return path
    raise FileNotFoundError("web UI is missing; rebuild the package")


class Handler(BaseHTTPRequestHandler):
    server_version = "artek-buddy"

    def log_message(self, fmt: str, *args) -> None:
        _log("client: " + (fmt % args))

    def _route(self) -> str:
        return self.path.split("?", 1)[0]

    def do_GET(self) -> None:
        path = self._route()
        if path == "/local/status":
            self._local_status()
            return
        if path == "/health" or path.startswith("/v1/") or path.startswith("/novnc/"):
            if path.startswith("/novnc/") and (self.headers.get("Upgrade") or "").lower() == "websocket":
                self._proxy_ws()
                return
            self._proxy()
            return
        self._static()

    def do_POST(self) -> None:
        path = self._route()
        if path == "/local/pair":
            self._local_pair()
            return
        if path == "/local/notify":
            self._local_notify()
            return
        if path.startswith("/v1/"):
            self._proxy()
            return
        self.send_error(404)

    def do_PATCH(self) -> None:
        if self._route().startswith("/v1/"):
            self._proxy()
            return
        self.send_error(404)

    def do_DELETE(self) -> None:
        if self._route().startswith("/v1/"):
            self._proxy()
            return
        self.send_error(404)

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Authorization, Content-Type, Accept")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PATCH, DELETE, OPTIONS")
        self.end_headers()

    def _json(self, status: int, payload: dict) -> None:
        data = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(data)

    def _local_only(self) -> bool:
        return self.client_address[0] in {"127.0.0.1", "::1"}

    def _local_status(self) -> None:
        if not self._local_only():
            self.send_error(403)
            return
        token = self.server.token  # type: ignore[attr-defined]
        url = self.server.upstream  # type: ignore[attr-defined]
        self._json(200, {"paired": bool(token), "url": url})

    def _local_pair(self) -> None:
        if not self._local_only():
            self.send_error(403)
            return
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b"{}"
        try:
            payload = json.loads(raw.decode("utf-8") or "{}")
        except (UnicodeDecodeError, json.JSONDecodeError):
            self._json(400, {"ok": False, "error": "invalid json"})
            return
        if not isinstance(payload, dict):
            self._json(400, {"ok": False, "error": "invalid json"})
            return
        code = str(payload.get("pairing_code") or "").strip()
        name = str(payload.get("name") or "This computer").strip() or "This computer"
        platform = str(payload.get("platform") or "linux").strip() or "linux"
        url = str(payload.get("url") or self.server.upstream).strip().rstrip("/")  # type: ignore[attr-defined]
        if not code:
            self._json(400, {"ok": False, "error": "pairing code required"})
            return
        if not url.startswith(("http://", "https://")):
            self._json(400, {"ok": False, "error": "invalid url"})
            return
        body = json.dumps(
            {"name": name[:80], "platform": platform[:40], "pairing_code": code}
        ).encode("utf-8")
        try:
            status, data = _host_request(
                url,
                "POST",
                "/v1/devices",
                body,
                {"Accept": "application/json", "Content-Type": "application/json", "Connection": "close"},
            )
        except OSError:
            _log("pair failed: host unreachable")
            self._json(502, {"ok": False, "error": "host unreachable"})
            return
        parsed: dict = {}
        if data:
            try:
                loaded = json.loads(data.decode("utf-8"))
                if isinstance(loaded, dict):
                    parsed = loaded
            except (UnicodeDecodeError, json.JSONDecodeError):
                parsed = {}
        if status != 200 or not parsed.get("token"):
            detail = parsed.get("detail")
            if isinstance(detail, dict):
                message = str(detail.get("message") or "pairing failed")
            elif isinstance(detail, str):
                message = detail
            else:
                message = "pairing failed"
            _log("pair failed status=%s" % status)
            self._json(status if 400 <= status < 600 else 502, {"ok": False, "error": message})
            return
        token = str(parsed["token"])
        _write_text(_config_dir() / "url", url, 0o644)
        _write_text(_config_dir() / "token", token, 0o600)
        self.server.upstream = url  # type: ignore[attr-defined]
        self.server.token = token  # type: ignore[attr-defined]
        _log("pair ok")
        self._json(
            200,
            {
                "ok": True,
                "device": {
                    "id": parsed.get("id"),
                    "name": parsed.get("name") or name,
                    "platform": parsed.get("platform") or platform,
                    "created_at": parsed.get("created_at"),
                },
            },
        )

    def _local_notify(self) -> None:
        if not self._local_only():
            self.send_error(403)
            return
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b"{}"
        try:
            payload = json.loads(raw.decode("utf-8") or "{}")
        except (UnicodeDecodeError, json.JSONDecodeError):
            self._json(400, {"ok": False, "error": "invalid json"})
            return
        if not isinstance(payload, dict):
            self._json(400, {"ok": False, "error": "invalid json"})
            return
        title = _notify_text(payload.get("title"), 80) or "Artek Buddy"
        body = _notify_text(payload.get("body"), 240)
        urgency = str(payload.get("urgency") or "normal").strip().lower()
        if urgency not in {"low", "normal", "critical"}:
            urgency = "normal"
        _desktop_notify(title, body, urgency)
        self._json(200, {"ok": True})

    def _proxy(self) -> None:
        upstream = urlsplit(self.server.upstream)  # type: ignore[attr-defined]
        token = self.server.token  # type: ignore[attr-defined]
        path = self.path
        body = b""
        length = int(self.headers.get("Content-Length") or 0)
        if length:
            body = self.rfile.read(length)
        headers = {
            "Accept": self.headers.get("Accept", "application/json"),
            "Authorization": f"Bearer {token}",
            "Connection": "close",
        }
        if body:
            headers["Content-Type"] = self.headers.get("Content-Type", "application/json")
        if upstream.scheme == "https":
            conn: http.client.HTTPConnection = http.client.HTTPSConnection(
                upstream.hostname or "127.0.0.1",
                upstream.port or 443,
                timeout=600,
                context=ssl.create_default_context(),
            )
        else:
            conn = http.client.HTTPConnection(
                upstream.hostname or "127.0.0.1",
                upstream.port or 80,
                timeout=600,
            )
        try:
            conn.request(self.command, path, body=body or None, headers=headers)
            resp = conn.getresponse()
            self.send_response(resp.status)
            skip = {"transfer-encoding", "connection", "keep-alive", "content-length"}
            for key, value in resp.getheaders():
                if key.lower() in skip:
                    continue
                self.send_header(key, value)
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            while True:
                chunk = resp.read1(16384) if hasattr(resp, "read1") else resp.read(16384)
                if not chunk:
                    break
                self.wfile.write(chunk)
                self.wfile.flush()
        except BrokenPipeError:
            return
        finally:
            conn.close()

    def _proxy_ws(self) -> None:
        upstream = urlsplit(self.server.upstream)  # type: ignore[attr-defined]
        token = self.server.token  # type: ignore[attr-defined]
        host = upstream.hostname or "127.0.0.1"
        port = upstream.port or (443 if upstream.scheme == "https" else 80)
        try:
            raw = socket.create_connection((host, port), timeout=30)
            sock: socket.socket = raw
            if upstream.scheme == "https":
                sock = ssl.create_default_context().wrap_socket(raw, server_hostname=host)
        except OSError:
            self.send_error(502, "host unreachable")
            return
        host_header = host if port in {80, 443} else f"{host}:{port}"
        lines = [
            f"{self.command} {self.path} HTTP/1.1",
            f"Host: {host_header}",
            "Upgrade: websocket",
            "Connection: Upgrade",
            f"Authorization: Bearer {token}",
        ]
        for key in (
            "Sec-WebSocket-Key",
            "Sec-WebSocket-Version",
            "Sec-WebSocket-Protocol",
            "Sec-WebSocket-Extensions",
            "Origin",
        ):
            value = self.headers.get(key)
            if value:
                lines.append(f"{key}: {value}")
        try:
            sock.sendall(("\r\n".join(lines) + "\r\n\r\n").encode("iso-8859-1"))
            buf = b""
            while b"\r\n\r\n" not in buf:
                chunk = sock.recv(4096)
                if not chunk:
                    break
                buf += chunk
            header, rest = buf.split(b"\r\n\r\n", 1) if b"\r\n\r\n" in buf else (buf, b"")
            first = header.split(b"\r\n", 1)[0]
            parts = first.split(None, 2)
            status = int(parts[1]) if len(parts) >= 2 and parts[1].isdigit() else 502
            # WebSocket clients require HTTP/1.1 101. BaseHTTPRequestHandler
            # defaults to HTTP/1.0, which leaves noVNC on a black canvas.
            out = [f"HTTP/1.1 {status} Switching Protocols"]
            skip = {b"transfer-encoding", b"connection", b"keep-alive", b"content-length"}
            have_upgrade = False
            for line in header.split(b"\r\n")[1:]:
                if b":" not in line:
                    continue
                key, value = line.split(b":", 1)
                if key.lower() in skip:
                    continue
                if key.lower() == b"upgrade":
                    have_upgrade = True
                out.append(f"{key.decode('latin1')}: {value.decode('latin1').strip()}")
            out.append("Connection: upgrade")
            if not have_upgrade:
                out.append("Upgrade: websocket")
            client = self.connection
            client.sendall(("\r\n".join(out) + "\r\n\r\n").encode("iso-8859-1") + rest)
            self.close_connection = True
            _log("novnc ws status=%s" % status)
            while True:
                readable, _, _ = select.select([client, sock], [], [], 60)
                if not readable:
                    continue
                if client in readable:
                    data = client.recv(16384)
                    if not data:
                        break
                    sock.sendall(data)
                if sock in readable:
                    data = sock.recv(16384)
                    if not data:
                        break
                    client.sendall(data)
        except (BrokenPipeError, OSError):
            return
        finally:
            try:
                sock.close()
            except OSError:
                pass

    def _static(self) -> None:
        root = self.server.web_root  # type: ignore[attr-defined]
        raw = self.path.split("?", 1)[0]
        if raw in {"", "/"}:
            raw = "/index.html"
        rel = Path(raw.lstrip("/"))
        target = (root / rel).resolve()
        try:
            target.relative_to(root.resolve())
        except ValueError:
            self.send_error(404)
            return
        if target.is_dir():
            target = target / "index.html"
        if not target.is_file():
            target = root / "index.html"
        data = target.read_bytes()
        ctype = mimetypes.guess_type(str(target))[0] or "application/octet-stream"
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


def _notify_text(value: object, limit: int) -> str:
    return " ".join(str(value or "").split())[:limit]


def _register_window(window: object) -> None:
    with _WINDOW_LOCK:
        if window not in _GTK_WINDOWS:
            _GTK_WINDOWS.append(window)


def _unregister_window(window: object) -> None:
    with _WINDOW_LOCK:
        try:
            _GTK_WINDOWS.remove(window)
        except ValueError:
            pass


def _apply_urgency(urgent: bool) -> None:
    def go() -> bool:
        with _WINDOW_LOCK:
            windows = list(_GTK_WINDOWS)
        for window in windows:
            setter = getattr(window, "set_urgency_hint", None)
            if setter is None:
                continue
            try:
                setter(bool(urgent))
            except Exception:
                pass
        return False

    try:
        from gi.repository import GLib

        GLib.idle_add(go)
    except Exception:
        go()


def _on_focus_in(*_args: object) -> bool:
    _apply_urgency(False)
    return False


def _on_gtk_active(window: object, *_args: object) -> None:
    is_active = getattr(window, "is_active", None)
    if callable(is_active) and is_active():
        _apply_urgency(False)


def _desktop_notify(title: str, body: str, urgency: str) -> None:
    _apply_urgency(True)
    if os.environ.get("ARTEK_BUDDY_NOTIFY") == "0":
        _log("notify skipped")
        return
    notify = shutil.which("notify-send")
    if not notify:
        _log("notify-send missing")
        return
    try:
        subprocess.run(
            [
                notify,
                "--app-name=Artek Buddy",
                f"--urgency={urgency}",
                "--",
                title,
                body,
            ],
            check=False,
            timeout=5,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except OSError:
        _log("notify-send failed")


def serve(url: str, token: str, port: int = 0) -> ThreadingHTTPServer:
    httpd = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    httpd.upstream = url
    httpd.token = token
    httpd.web_root = web_root()
    return httpd


def _open_webkit2(local_url: str) -> bool:
    import gi

    gi.require_version("Gtk", "3.0")
    loaded = None
    for version in ("4.1", "4.0"):
        try:
            gi.require_version("WebKit2", version)
            loaded = version
            break
        except ValueError:
            continue
    if loaded is None:
        raise RuntimeError("WebKit2 typelib not found")
    from gi.repository import Gtk, WebKit2

    window = Gtk.Window(title="Artek Buddy")
    window.set_default_size(1440, 900)
    window.connect("destroy", lambda *_args: (_unregister_window(window), Gtk.main_quit()))
    window.connect("focus-in-event", _on_focus_in)
    view = WebKit2.WebView()
    view.load_uri(local_url)
    window.add(view)
    _register_window(window)
    window.show_all()
    Gtk.main()
    return True


def _open_webkit6(local_url: str) -> bool:
    import gi

    gi.require_version("Gtk", "4.0")
    gi.require_version("WebKit", "6.0")
    from gi.repository import Gtk, WebKit

    def on_activate(app: Gtk.Application) -> None:
        window = Gtk.ApplicationWindow(application=app, title="Artek Buddy")
        window.set_default_size(1440, 900)
        window.connect("notify::is-active", _on_gtk_active)
        window.connect("destroy", lambda *_args: _unregister_window(window))
        view = WebKit.WebView()
        view.load_uri(local_url)
        window.set_child(view)
        _register_window(window)
        window.present()

    app = Gtk.Application(application_id="local.artek.buddy")
    app.connect("activate", on_activate)
    app.run(None)
    return True


def open_window(local_url: str) -> bool:
    try:
        return _open_webkit2(local_url)
    except Exception:
        _log("webkit2 window failed:\n" + traceback.format_exc())
    try:
        return _open_webkit6(local_url)
    except Exception:
        _log("webkit6 window failed:\n" + traceback.format_exc())
    return False


def main() -> None:
    parser = argparse.ArgumentParser(prog="artek-buddy")
    parser.add_argument("--serve", action="store_true", help="proxy only; do not open a window")
    parser.add_argument("--port", type=int, default=0)
    args = parser.parse_args()
    url = _load_url()
    token = _load_token()
    _log(
        "start token_ok=%s url_scheme=%s"
        % (bool(token), urlsplit(url).scheme or "none")
    )
    try:
        httpd = serve(url, token, args.port)
    except Exception:
        _log("proxy failed:\n" + traceback.format_exc())
        sys.exit(2)
    host, port = httpd.server_address[:2]
    local = f"http://{host}:{port}/"
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    if args.serve:
        print(local)
        try:
            thread.join()
        except KeyboardInterrupt:
            httpd.shutdown()
        return
    if open_window(local):
        httpd.shutdown()
        return
    _log("no webkit window; opening the system browser")
    webbrowser.open(local)
    try:
        thread.join()
    except KeyboardInterrupt:
        httpd.shutdown()


if __name__ == "__main__":
    main()
