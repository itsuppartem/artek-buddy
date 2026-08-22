#!/usr/bin/env python3
"""Desktop shell: local proxy + web UI. Credentials stay on this machine."""

from __future__ import annotations

import argparse
import base64
import http.client
import ipaddress
import json
import mimetypes
import os
import re
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
from urllib.parse import urlencode, urlsplit

_CLIENT_DIR = Path(__file__).resolve().parent
if str(_CLIENT_DIR) not in sys.path:
    sys.path.insert(0, str(_CLIENT_DIR))

from owner_paths import (
    _owner_path_status,
    inspect_owner_path,
    owner_downloads_dir,
    unique_download_dest,
)
from window_chrome import (
    _apply_urgency,
    _gtk_choose_save_path,
    _has_gtk_window,
    _notify_text,
    _on_focus_in,
    _on_gtk_active,
    _register_window,
    _unregister_window,
    apply_window_icon,
    notify_icon_args,
)

WEB_ROOTS = (
    Path("/usr/lib/artek-buddy-client/web"),
    Path(__file__).with_name("web") / "dist",
)


_NOVNC_LOG = re.compile(r"/novnc/\S+")
_CGNAT = ipaddress.ip_network("100.64.0.0/10")
OWNER_FILE_MAX = 1_000_000
OWNER_OUTPUT_MAX = 200_000
OWNER_EXEC_TIMEOUT = 60
ATTACH_FILE_MAX = 25 * 1024 * 1024
ATTACH_TOTAL_MAX = 50 * 1024 * 1024
ATTACH_MAX_FILES = 10


save_path_chooser = None


def choose_save_path(name: str) -> Path | None:
    """Ask where to put the file. The .deb window uses a GTK Save dialog."""
    hook = save_path_chooser
    if callable(hook):
        return hook(name)
    if os.environ.get("ARTEK_SAVE_NO_DIALOG") == "1":
        return unique_download_dest(owner_downloads_dir(), name)
    if _has_gtk_window():
        return _gtk_choose_save_path(name)
    return unique_download_dest(owner_downloads_dir(), name)


def _redact_client_log(message: str) -> str:
    return _NOVNC_LOG.sub("/novnc/[redacted]", message)


def pairing_url_allowed(url: str) -> bool:
    parsed = urlsplit(url)
    if parsed.scheme not in {"http", "https"}:
        return False
    try:
        host = (parsed.hostname or "").lower()
        port = parsed.port
    except ValueError:
        return False
    if not host:
        return False
    if port is not None and not (1 <= port <= 65535):
        return False
    if host in {"localhost", "127.0.0.1", "::1"}:
        return True
    if host.endswith(".ts.net"):
        return True
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return False
    return bool(ip.is_loopback or ip.is_private or ip in _CGNAT)


def proxy_origin_allowed(origin: str | None, fetch_site: str | None, proxy_port: int) -> bool:
    if (fetch_site or "").lower() == "cross-site":
        return False
    if not origin:
        return True
    parsed = urlsplit(origin)
    host = (parsed.hostname or "").lower()
    if host not in {"127.0.0.1", "localhost", "::1"}:
        return False
    port = parsed.port
    if port is None:
        port = 443 if parsed.scheme == "https" else 80
    return port == proxy_port


def _log(message: str) -> None:
    text = _redact_client_log(message.rstrip())
    try:
        path = Path.home() / ".config" / "artek-buddy" / "client.log"
        path.parent.mkdir(parents=True, exist_ok=True)
        existed = path.exists()
        with path.open("a", encoding="utf-8") as handle:
            handle.write(text + "\n")
        if not existed or path.stat().st_mode & 0o077:
            path.chmod(0o600)
    except OSError:
        pass
    sys.stderr.write(text + "\n")


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


def _host_request(
    url: str, method: str, path: str, body: bytes, headers: dict[str, str]
) -> tuple[int, bytes]:
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

    def _accept_browser(self) -> bool:
        port = int(self.server.server_address[1])
        if proxy_origin_allowed(
            self.headers.get("Origin"), self.headers.get("Sec-Fetch-Site"), port
        ):
            return True
        self.send_error(403, "cross-origin request blocked")
        return False

    def _route(self) -> str:
        return self.path.split("?", 1)[0]

    def do_GET(self) -> None:
        path = self._route()
        if path == "/local/status":
            self._local_status()
            return
        if path == "/health" or path.startswith("/v1/") or path.startswith("/novnc/"):
            if (
                path.startswith("/novnc/")
                and (self.headers.get("Upgrade") or "").lower() == "websocket"
            ):
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
        if path == "/local/unpair":
            self._local_unpair()
            return
        if path == "/local/notify":
            self._local_notify()
            return
        if path == "/local/owner-read":
            self._local_owner_read()
            return
        if path == "/local/owner-write":
            self._local_owner_write()
            return
        if path == "/local/owner-list":
            self._local_owner_list()
            return
        if path == "/local/owner-exec":
            self._local_owner_exec()
            return
        if path == "/local/save-artifact":
            self._local_save_artifact()
            return
        if path == "/local/save-home-file":
            self._local_save_home_file()
            return
        if path == "/local/attach-files":
            self._local_attach_files()
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
        if not self._accept_browser():
            return
        self.send_response(204)
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
        if not url.startswith(("http://", "https://")) or not pairing_url_allowed(url):
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
                {
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                    "Connection": "close",
                },
            )
        except ValueError:
            _log("pair failed: invalid url")
            self._json(400, {"ok": False, "error": "invalid url"})
            return
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

    def _local_unpair(self) -> None:
        if not self._local_only():
            self.send_error(403)
            return
        path = _config_dir() / "token"
        try:
            path.unlink()
        except FileNotFoundError:
            pass
        except OSError:
            self._json(500, {"ok": False, "error": "could not forget this computer"})
            return
        self.server.token = ""  # type: ignore[attr-defined]
        _log("unpair ok")
        self._json(200, {"ok": True, "paired": False})

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

    def _local_owner_read(self) -> None:
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
        path, err = inspect_owner_path(str(payload.get("path") or ""))
        if path is None:
            self._json(_owner_path_status(err), {"ok": False, "error": err})
            return
        try:
            data = path.read_bytes()
        except OSError:
            self._json(404, {"ok": False, "error": "could not read file"})
            return
        if len(data) > OWNER_FILE_MAX:
            self._json(400, {"ok": False, "error": "file is larger than 1 MB"})
            return
        out: dict = {
            "ok": True,
            "name": path.name,
            "bytes": len(data),
            "content_base64": base64.b64encode(data).decode("ascii"),
        }
        try:
            out["text"] = data.decode("utf-8")
        except UnicodeDecodeError:
            pass
        self._json(200, out)

    def _local_attach_files(self) -> None:
        if not self._local_only():
            self.send_error(403)
            return
        payload = self._local_json_body()
        if payload is None:
            return
        raw_paths = payload.get("paths")
        if not isinstance(raw_paths, list) or not raw_paths:
            self._json(400, {"ok": False, "error": "paths required"})
            return
        if len(raw_paths) > ATTACH_MAX_FILES:
            self._json(400, {"ok": False, "error": "At most 10 files"})
            return
        files: list[dict] = []
        total = 0
        for raw in raw_paths:
            path, err = inspect_owner_path(str(raw or ""))
            if path is None:
                self._json(_owner_path_status(err), {"ok": False, "error": err})
                return
            try:
                data = path.read_bytes()
            except OSError:
                self._json(404, {"ok": False, "error": "could not read file"})
                return
            if len(data) > ATTACH_FILE_MAX:
                self._json(400, {"ok": False, "error": f"{path.name} is larger than 25 MB"})
                return
            total += len(data)
            if total > ATTACH_TOTAL_MAX:
                self._json(400, {"ok": False, "error": "Those files are too large together"})
                return
            mime, _enc = mimetypes.guess_type(path.name)
            files.append(
                {
                    "name": path.name,
                    "type": mime or "application/octet-stream",
                    "bytes": len(data),
                    "content_base64": base64.b64encode(data).decode("ascii"),
                }
            )
        self._json(200, {"ok": True, "files": files})

    def _local_json_body(self) -> dict | None:
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b"{}"
        try:
            payload = json.loads(raw.decode("utf-8") or "{}")
        except (UnicodeDecodeError, json.JSONDecodeError):
            self._json(400, {"ok": False, "error": "invalid json"})
            return None
        if not isinstance(payload, dict):
            self._json(400, {"ok": False, "error": "invalid json"})
            return None
        return payload

    def _local_owner_write(self) -> None:
        if not self._local_only():
            self.send_error(403)
            return
        payload = self._local_json_body()
        if payload is None:
            return
        path, err = inspect_owner_path(str(payload.get("path") or ""), must_exist=False)
        if path is None:
            self._json(_owner_path_status(err), {"ok": False, "error": err})
            return
        data = b""
        if payload.get("content_base64"):
            try:
                data = base64.b64decode(str(payload.get("content_base64")))
            except (ValueError, TypeError):
                self._json(400, {"ok": False, "error": "invalid content_base64"})
                return
        elif payload.get("text") is not None:
            data = str(payload.get("text")).encode()
        else:
            self._json(400, {"ok": False, "error": "text or content_base64 required"})
            return
        if len(data) > OWNER_FILE_MAX:
            self._json(400, {"ok": False, "error": "file is larger than 1 MB"})
            return
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        except OSError:
            self._json(500, {"ok": False, "error": "could not write file"})
            return
        self._json(200, {"ok": True, "path": str(path), "name": path.name, "bytes": len(data)})

    def _local_owner_list(self) -> None:
        if not self._local_only():
            self.send_error(403)
            return
        payload = self._local_json_body()
        if payload is None:
            return
        path, err = inspect_owner_path(
            str(payload.get("path") or "~"), must_exist=True, as_dir=True
        )
        if path is None:
            self._json(_owner_path_status(err), {"ok": False, "error": err})
            return
        entries: list[dict] = []
        try:
            names = sorted(path.iterdir(), key=lambda item: item.name.lower())
        except OSError:
            self._json(500, {"ok": False, "error": "could not list folder"})
            return
        for item in names[:500]:
            kind = "dir" if item.is_dir() else "file"
            size = None
            if kind == "file":
                try:
                    size = item.stat().st_size
                except OSError:
                    size = None
            entries.append({"name": item.name, "kind": kind, "size": size})
        self._json(200, {"ok": True, "path": str(path), "entries": entries})

    def _local_owner_exec(self) -> None:
        if not self._local_only():
            self.send_error(403)
            return
        payload = self._local_json_body()
        if payload is None:
            return
        command = str(payload.get("command") or "").strip()
        if not command:
            self._json(400, {"ok": False, "error": "command required"})
            return
        if len(command) > 8000:
            self._json(400, {"ok": False, "error": "command is too long"})
            return
        cwd, err = inspect_owner_path(str(payload.get("cwd") or "~"), must_exist=True, as_dir=True)
        if cwd is None:
            self._json(_owner_path_status(err), {"ok": False, "error": f"cwd: {err}"})
            return
        try:
            proc = subprocess.run(
                command,
                shell=True,
                cwd=str(cwd),
                capture_output=True,
                timeout=OWNER_EXEC_TIMEOUT,
                text=True,
                errors="replace",
            )
        except subprocess.TimeoutExpired:
            self._json(
                200,
                {
                    "ok": False,
                    "error": "command timed out",
                    "stdout": "",
                    "stderr": "",
                    "exit_code": 124,
                },
            )
            return
        except OSError as exc:
            self._json(500, {"ok": False, "error": str(exc)})
            return
        stdout = proc.stdout[:OWNER_OUTPUT_MAX]
        stderr = proc.stderr[:OWNER_OUTPUT_MAX]
        self._json(
            200,
            {
                "ok": True,
                "stdout": stdout,
                "stderr": stderr,
                "exit_code": proc.returncode,
            },
        )

    def _local_save_artifact(self) -> None:
        if not self._local_only():
            self.send_error(403)
            return
        payload = self._local_json_body()
        if payload is None:
            return
        artifact_id = str(payload.get("artifact_id") or payload.get("artifactId") or "").strip()
        name = str(payload.get("name") or "file").strip() or "file"
        if not artifact_id or "/" in artifact_id or "\\" in artifact_id:
            self._json(400, {"ok": False, "error": "artifact_id required"})
            return
        token = self.server.token  # type: ignore[attr-defined]
        url = self.server.upstream  # type: ignore[attr-defined]
        if not token:
            self._json(
                401,
                {
                    "ok": False,
                    "error": "This computer is no longer authorized. Pair it again to continue.",
                },
            )
            return
        try:
            status, data = _host_request(
                url,
                "GET",
                f"/v1/artifacts/{artifact_id}",
                b"",
                {
                    "Accept": "*/*",
                    "Authorization": f"Bearer {token}",
                    "Connection": "close",
                },
            )
        except OSError:
            self._json(502, {"ok": False, "error": "Could not reach the host"})
            return
        if status != 200 or not data:
            self._json(
                404 if status == 404 else 502,
                {"ok": False, "error": "Could not download that file"},
            )
            return
        self._write_chosen_file(data, name)

    def _local_save_home_file(self) -> None:
        if not self._local_only():
            self.send_error(403)
            return
        payload = self._local_json_body()
        if payload is None:
            return
        bot_id = str(payload.get("bot_id") or payload.get("botId") or "").strip()
        rel = str(payload.get("path") or "").strip().replace("\\", "/")
        name = str(payload.get("name") or "file").strip() or "file"
        if not bot_id or "/" in bot_id or "\\" in bot_id or not bot_id.startswith("bot_"):
            self._json(400, {"ok": False, "error": "bot_id required"})
            return
        if not rel or ".." in rel.split("/"):
            self._json(400, {"ok": False, "error": "path required"})
            return
        token = self.server.token  # type: ignore[attr-defined]
        url = self.server.upstream  # type: ignore[attr-defined]
        if not token:
            self._json(
                401,
                {
                    "ok": False,
                    "error": "This computer is no longer authorized. Pair it again to continue.",
                },
            )
            return
        query = urlencode({"path": rel})
        try:
            status, data = _host_request(
                url,
                "GET",
                f"/v1/computer/{bot_id}/files/raw?{query}",
                b"",
                {
                    "Accept": "*/*",
                    "Authorization": f"Bearer {token}",
                    "Connection": "close",
                },
            )
        except OSError:
            self._json(502, {"ok": False, "error": "Could not reach the host"})
            return
        if status != 200 or not data:
            self._json(
                404 if status == 404 else 502,
                {"ok": False, "error": "Could not download that file"},
            )
            return
        self._write_chosen_file(data, name)

    def _write_chosen_file(self, data: bytes, name: str) -> None:
        dest = choose_save_path(name)
        if dest is None:
            self._json(409, {"ok": False, "cancelled": True, "error": "Save cancelled"})
            return
        try:
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(data)
        except OSError:
            self._json(500, {"ok": False, "error": "Could not write the file"})
            return
        self._json(200, {"ok": True, "path": str(dest), "name": dest.name, "bytes": len(data)})

    def _proxy(self) -> None:
        if not self._accept_browser():
            return
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
        except (BrokenPipeError, ConnectionResetError):
            return
        finally:
            conn.close()

    def _proxy_ws(self) -> None:
        if not self._accept_browser():
            return
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
                *notify_icon_args(),
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
    apply_window_icon(window)
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
        apply_window_icon(window)
        try:
            Gtk.Window.set_default_icon_name("artek-buddy")
        except Exception:
            pass
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
    _log("start token_ok=%s url_scheme=%s" % (bool(token), urlsplit(url).scheme or "none"))
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
