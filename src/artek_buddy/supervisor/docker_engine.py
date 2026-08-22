from __future__ import annotations

import json
import socket
from http.client import HTTPConnection
from typing import Any
from urllib.parse import quote


class UnixHTTPConnection(HTTPConnection):
    def __init__(self, path: str, timeout: float = 60) -> None:
        super().__init__("localhost", timeout=timeout)
        self.unix_path = path

    def connect(self) -> None:
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.settimeout(self.timeout)
        sock.connect(self.unix_path)
        self.sock = sock


class DockerEngine:
    def __init__(self, socket_path: str = "/var/run/docker.sock") -> None:
        self.socket_path = socket_path

    def request(
        self,
        method: str,
        path: str,
        body: Any | None = None,
        timeout: float = 60,
    ) -> tuple[int, Any]:
        payload = None
        headers = {"Content-Type": "application/json"}
        if body is not None:
            payload = json.dumps(body).encode("utf-8")
            headers["Content-Length"] = str(len(payload))
        conn = UnixHTTPConnection(self.socket_path, timeout=timeout)
        try:
            conn.request(method, path, body=payload, headers=headers)
            resp = conn.getresponse()
            raw = resp.read()
            parsed: Any = {}
            if raw:
                try:
                    parsed = json.loads(raw.decode("utf-8"))
                except json.JSONDecodeError:
                    parsed = raw
            return resp.status, parsed
        finally:
            conn.close()

    def inspect(self, container_id: str) -> dict[str, Any] | None:
        status, data = self.request("GET", f"/containers/{quote(container_id)}/json")
        if status == 404:
            return None
        if status >= 300 or not isinstance(data, dict):
            raise RuntimeError(f"docker inspect failed: {status}")
        return data

    def find_by_name(self, name: str) -> dict[str, Any] | None:
        status, data = self.request(
            "GET",
            f"/containers/json?all=1&filters={quote(json.dumps({'name': [name]}))}",
        )
        if status >= 300 or not isinstance(data, list) or not data:
            return None
        return self.inspect(data[0]["Id"])

    def ensure_network(self, name: str = "artek-computers") -> str:
        status, data = self.request("GET", f"/networks/{quote(name)}")
        if status == 200 and isinstance(data, dict):
            return name
        status, created = self.request(
            "POST",
            "/networks/create",
            {
                "Name": name,
                "CheckDuplicate": True,
                "Driver": "bridge",
                "Internal": False,
                "Options": {"com.docker.network.bridge.enable_icc": "false"},
            },
        )
        if status in {201, 409} or (isinstance(created, dict) and created.get("Id")):
            return name
        if status >= 300:
            raise RuntimeError(f"docker network create failed: {status} {created}")
        return name

    def create(self, spec: dict[str, Any]) -> str:
        name = spec.pop("name")
        status, data = self.request("POST", f"/containers/create?name={quote(name)}", spec)
        if status >= 300 or not isinstance(data, dict) or not data.get("Id"):
            raise RuntimeError(f"docker create failed: {status} {data}")
        return str(data["Id"])

    def start(self, container_id: str) -> None:
        status, data = self.request("POST", f"/containers/{quote(container_id)}/start")
        if status not in {204, 304} and status >= 300:
            raise RuntimeError(f"docker start failed: {status} {data}")

    def stop(self, container_id: str, timeout: int = 10) -> None:
        status, data = self.request(
            "POST",
            f"/containers/{quote(container_id)}/stop?t={timeout}",
        )
        if status not in {204, 304} and status >= 300:
            raise RuntimeError(f"docker stop failed: {status} {data}")

    def remove(self, container_id: str) -> None:
        status, data = self.request("DELETE", f"/containers/{quote(container_id)}?force=1")
        if status not in {204, 404} and status >= 300:
            raise RuntimeError(f"docker remove failed: {status} {data}")

    def exec(self, container_id: str, command: str) -> tuple[int, str]:
        status, created = self.request(
            "POST",
            f"/containers/{quote(container_id)}/exec",
            {
                "AttachStdout": True,
                "AttachStderr": True,
                "Cmd": ["bash", "-lc", command],
            },
        )
        if status >= 300 or not isinstance(created, dict) or not created.get("Id"):
            raise RuntimeError(f"docker exec create failed: {status} {created}")
        exec_id = created["Id"]
        conn = UnixHTTPConnection(self.socket_path, timeout=60)
        try:
            body = json.dumps({"Detach": False, "Tty": False}).encode("utf-8")
            conn.request(
                "POST",
                f"/exec/{quote(exec_id)}/start",
                body=body,
                headers={"Content-Type": "application/json", "Content-Length": str(len(body))},
            )
            resp = conn.getresponse()
            raw = resp.read()
        finally:
            conn.close()
        text = _demux_docker(raw)
        inspect_status, info = self.request("GET", f"/exec/{quote(exec_id)}/json")
        code = 1
        if inspect_status < 300 and isinstance(info, dict):
            code = int(info.get("ExitCode") or 0)
        return code, text

    def get_file(self, container_id: str, path: str) -> bytes:
        code, text = self.exec(container_id, f"base64 -w0 {shell_path(path)} 2>/dev/null")
        if code != 0:
            raise FileNotFoundError(path)
        import base64

        return base64.b64decode(text.strip())


def shell_path(path: str) -> str:
    from artek_buddy.supervisor.logic import shell_quote

    return shell_quote(path)


def published_port(inspect: dict[str, Any], container_port: str) -> int | None:
    ports = (inspect.get("NetworkSettings") or {}).get("Ports") or {}
    bindings = ports.get(f"{container_port}/tcp") or []
    if not bindings:
        return None
    try:
        return int(bindings[0].get("HostPort") or 0) or None
    except (TypeError, ValueError):
        return None


def _demux_docker(raw: bytes) -> str:
    if not raw:
        return ""
    if len(raw) >= 8 and raw[0] in {1, 2} and raw[1:4] == b"\x00\x00\x00":
        chunks: list[bytes] = []
        offset = 0
        while offset + 8 <= len(raw):
            size = int.from_bytes(raw[offset + 4 : offset + 8], "big")
            chunks.append(raw[offset + 8 : offset + 8 + size])
            offset += 8 + size
        return b"".join(chunks).decode("utf-8", errors="replace")
    return raw.decode("utf-8", errors="replace")
