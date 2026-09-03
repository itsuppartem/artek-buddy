from __future__ import annotations

import base64
import hmac
import json
import mimetypes
import subprocess
from typing import Any
from urllib.parse import urlencode

from owner_paths import (
    _owner_path_status,
    inspect_owner_exec_writes,
    inspect_owner_path,
)
from pairing import _log, _write_text, pairing_url_allowed
from proxy_common import (
    ATTACH_FILE_MAX,
    ATTACH_MAX_FILES,
    ATTACH_TOTAL_MAX,
    LOCAL_JSON_MAX,
    LOCAL_NONCE_HEADER,
    OWNER_EXEC_TIMEOUT,
    OWNER_FILE_MAX,
    OWNER_OUTPUT_MAX,
    _host_request,
    _json_content_type,
    choose_save_path,
    local_rpc_origin_allowed,
    proxy_host_allowed,
)
from window_chrome import _notify_text, gtk_window_active


def _proxy_mod() -> Any:
    import proxy

    return proxy


class LocalRpcMixin:
    def _accept_local(self, *, mutating: bool) -> bool:
        if not self._local_only():
            self.send_error(403, "forbidden")
            return False
        port = int(self.server.server_address[1])
        if not proxy_host_allowed(self.headers.get("Host"), port):
            self.send_error(403, "forbidden")
            return False
        if not local_rpc_origin_allowed(
            self.headers.get("Origin"),
            self.headers.get("Sec-Fetch-Site"),
            port,
            require_origin=mutating,
        ):
            self.send_error(403, "forbidden")
            return False
        if not mutating:
            return True
        if not _json_content_type(self.headers.get("Content-Type")):
            self.send_error(403, "forbidden")
            return False
        raw_len = self.headers.get("Content-Length") or "0"
        try:
            length = int(raw_len)
        except ValueError:
            self.send_error(400, "invalid content-length")
            return False
        if length < 0:
            self.send_error(400, "invalid content-length")
            return False
        limit = ATTACH_TOTAL_MAX * 2 if self._route() == "/local/attach-files" else LOCAL_JSON_MAX
        if length > limit:
            self.send_error(413, "payload too large")
            return False
        expected = getattr(self.server, "local_nonce", "") or ""
        given = self.headers.get(LOCAL_NONCE_HEADER) or ""
        if not expected or not hmac.compare_digest(given, expected):
            self.send_error(403, "forbidden")
            return False
        return True

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
        nonce = getattr(self.server, "local_nonce", "") or ""
        self._json(
            200,
            {
                "paired": bool(token),
                "url": url,
                "nonce": nonce,
                "window_active": gtk_window_active(),
            },
        )

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
        _write_text(_proxy_mod()._config_dir() / "url", url, 0o644)
        _write_text(_proxy_mod()._config_dir() / "token", token, 0o600)
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
        path = _proxy_mod()._config_dir() / "token"
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
        tag = _notify_text(payload.get("tag"), 80)
        _proxy_mod()._desktop_notify(title, body, urgency, tag)
        self._json(200, {"ok": True})

    def _local_notify_dismiss(self) -> None:
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
        tag = _notify_text(payload.get("tag"), 80)
        if not tag:
            self._json(400, {"ok": False, "error": "tag required"})
            return
        _proxy_mod()._desktop_dismiss(tag)
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
        write_err = inspect_owner_exec_writes(command)
        if write_err:
            self._json(_owner_path_status(write_err), {"ok": False, "error": write_err})
            return
        try:
            # Loopback owner-exec is the paired .deb talking to this PC, not the
            # sandbox. See THREAT-MODEL.md (Owner $HOME / Open by design).
            proc = _proxy_mod().subprocess.run(  # lgtm[py/command-line-injection]
                command,
                shell=True,
                cwd=str(cwd),
                capture_output=True,
                timeout=OWNER_EXEC_TIMEOUT,
                text=True,
                errors="replace",
                env=_proxy_mod().owner_exec_environment(),
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
