from __future__ import annotations

import json
import logging
import os
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

from artek_buddy.auth import supervisor_token
from artek_buddy.supervisor.docker_engine import DockerEngine, published_port
from artek_buddy.supervisor.logic import (
    action_command,
    input_command,
    interactive_screen_command,
    observe_command,
    shell_quote,
)

log = logging.getLogger("artek_buddy.supervisor")

SAFE_HOME = re.compile(r"^[A-Za-z0-9._-]+$")


class SupervisorState:
    def __init__(self) -> None:
        self.engine = DockerEngine(os.environ.get("DOCKER_SOCKET", "/var/run/docker.sock"))
        self.token = supervisor_token(
            os.environ.get("AGENT_HTTP_TOKEN", ""),
            os.environ.get("SANDBOX_SUPERVISOR_TOKEN", ""),
        )
        self.image = os.environ.get("COMPUTER_IMAGE", "artek-buddy-computer:local")
        self.data_dir = Path(os.environ.get("AGENT_DATA_DIR", "/data"))


STATE = SupervisorState()


def container_name(home_key: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9_.-]", "-", home_key).strip("-") or "home"
    return f"artek-bot-{safe}"


def home_dir(home_key: str) -> Path:
    if not SAFE_HOME.match(home_key):
        raise ValueError("invalid home key")
    path = STATE.data_dir / "homes" / home_key
    path.mkdir(parents=True, exist_ok=True)
    return path


def screen_payload(inspect: dict[str, Any], interactive: bool) -> dict[str, Any]:
    view = published_port(inspect, "6080")
    control = published_port(inspect, "6081")
    port = control if interactive and control else view
    return {
        "id": inspect.get("Id"),
        "name": (inspect.get("Name") or "").lstrip("/"),
        "running": (inspect.get("State") or {}).get("Running") is True,
        "view_port": view,
        "control_port": control,
        "screen_url": f"http://127.0.0.1:{port}/embed.html" if port else None,
    }


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt: str, *args: Any) -> None:
        log.info(fmt, *args)

    def _auth(self) -> bool:
        header = self.headers.get("Authorization", "")
        return bool(STATE.token) and header == f"Bearer {STATE.token}"

    def _json(self, status: int, payload: Any) -> None:
        data = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _read(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b"{}"
        try:
            parsed = json.loads(raw.decode("utf-8") or "{}")
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}

    def _parts(self) -> list[str]:
        return [unquote(part) for part in self.path.split("?", 1)[0].strip("/").split("/") if part]

    def do_GET(self) -> None:
        parts = self._parts()
        if parts == ["health"]:
            self._json(200, {"ok": True})
            return
        if not self._auth():
            self._json(401, {"error": "unauthorized"})
            return
        if len(parts) == 2 and parts[0] == "computers":
            inspect = STATE.engine.inspect(parts[1])
            if inspect is None:
                self._json(404, {"error": "not found"})
                return
            self._json(200, screen_payload(inspect, False))
            return
        if len(parts) == 3 and parts[0] == "computers" and parts[2] == "files":
            self._files(parts[1], write=False)
            return
        self._json(404, {"error": "not found"})

    def do_POST(self) -> None:
        if not self._auth():
            self._json(401, {"error": "unauthorized"})
            return
        parts = self._parts()
        body = self._read()
        try:
            if parts == ["computers"]:
                self._create(body)
                return
            if len(parts) == 3 and parts[0] == "computers":
                cid, action = parts[1], parts[2]
                if action == "stop":
                    STATE.engine.stop(cid)
                    self._json(200, {"ok": True})
                    return
                if action == "screen-mode":
                    self._screen_mode(cid, body)
                    return
                if action == "observe":
                    self._observe(cid, body)
                    return
                if action == "actions":
                    code, text = STATE.engine.exec(cid, action_command(list(body.get("actions") or [])))
                    self._json(200, {"ok": code == 0, "output": text})
                    return
                if action == "exec":
                    code, text = STATE.engine.exec(cid, str(body.get("command") or "true"))
                    self._json(200, {"ok": code == 0, "exit_code": code, "output": text})
                    return
                if action == "input":
                    code, text = STATE.engine.exec(
                        cid,
                        input_command(str(body.get("kind") or "click"), dict(body.get("payload") or {})),
                    )
                    self._json(200, {"ok": code == 0, "output": text})
                    return
                if action == "files":
                    self._files(cid, write=True, body=body)
                    return
        except Exception as err:
            log.exception("supervisor error")
            self._json(500, {"error": str(err)})
            return
        self._json(404, {"error": "not found"})

    def do_DELETE(self) -> None:
        if not self._auth():
            self._json(401, {"error": "unauthorized"})
            return
        parts = self._parts()
        if len(parts) == 2 and parts[0] == "computers":
            STATE.engine.remove(parts[1])
            self._json(200, {"ok": True})
            return
        self._json(404, {"error": "not found"})

    def _create(self, body: dict[str, Any]) -> None:
        home_key = str(body.get("home_key") or "")
        bot_id = str(body.get("bot_id") or "")
        if not home_key or not bot_id:
            self._json(400, {"error": "home_key and bot_id required"})
            return
        name = container_name(home_key)
        home = home_dir(home_key)
        existing = STATE.engine.find_by_name(name)
        if existing and (existing.get("Config") or {}).get("Image") == STATE.image:
            if not (existing.get("State") or {}).get("Running"):
                STATE.engine.start(existing["Id"])
                existing = STATE.engine.inspect(existing["Id"]) or existing
            self._json(200, screen_payload(existing, False))
            return
        if existing:
            STATE.engine.remove(existing["Id"])
        network = STATE.engine.ensure_network("artek-computers")
        spec = {
            "name": name,
            "Image": STATE.image,
            "Hostname": name,
            "Env": ["DISPLAY=:1", "HOME=/home/artek"],
            "Labels": {
                "artek.managed": "true",
                "artek.bot_id": bot_id,
                "artek.home_key": home_key,
            },
            "ExposedPorts": {"6080/tcp": {}, "6081/tcp": {}},
            "HostConfig": {
                "Binds": [f"{home}:/home/artek"],
                "PortBindings": {
                    "6080/tcp": [{"HostIp": "127.0.0.1", "HostPort": "0"}],
                    "6081/tcp": [{"HostIp": "127.0.0.1", "HostPort": "0"}],
                },
                "NetworkMode": network,
                "SecurityOpt": ["no-new-privileges:true"],
                "ShmSize": 268435456,
                "RestartPolicy": {"Name": "no"},
            },
        }
        cid = STATE.engine.create(spec)
        STATE.engine.start(cid)
        inspect = STATE.engine.inspect(cid)
        if inspect is None:
            raise RuntimeError("container vanished after start")
        self._json(201, screen_payload(inspect, False))

    def _screen_mode(self, cid: str, body: dict[str, Any]) -> None:
        interactive = bool(body.get("interactive"))
        token = str(body.get("control_token") or "") or None
        command = interactive_screen_command(interactive, token)
        code, text = STATE.engine.exec(cid, command)
        inspect = STATE.engine.inspect(cid)
        if inspect is None:
            self._json(404, {"error": "not found"})
            return
        payload = screen_payload(inspect, interactive)
        payload["ok"] = code == 0
        payload["output"] = text
        self._json(200 if code == 0 else 500, payload)

    def _observe(self, cid: str, body: dict[str, Any] | None = None) -> None:
        import base64

        include_image = bool((body or {}).get("include_image"))
        code, text = STATE.engine.exec(cid, observe_command(include_image=include_image))
        payload: dict[str, Any] = {"ok": code == 0, "output": text}
        if include_image and "PNG /tmp/artek/observe.png" in text:
            try:
                payload["image_png_base64"] = base64.b64encode(
                    STATE.engine.get_file(cid, "/tmp/artek/observe.png")
                ).decode("ascii")
            except Exception:
                pass
        self._json(200, payload)

    def _files(self, cid: str, write: bool, body: dict[str, Any] | None = None) -> None:
        query = parse_qs(urlparse(self.path).query)
        rel = str((body or {}).get("path") or (query.get("path") or ["/"])[0] or "/")
        if ".." in rel or rel.startswith("/"):
            target = "/home/artek" + (rel if rel.startswith("/") else "/" + rel)
        else:
            target = "/home/artek/" + rel
        if ".." in target:
            self._json(400, {"error": "invalid path"})
            return
        if write and body and "content" in body:
            content = str(body.get("content") or "")
            code, text = STATE.engine.exec(
                cid,
                f"mkdir -p $(dirname {shell_quote(target)}) && cat > {shell_quote(target)} <<'ARTEK_EOF'\n{content}\nARTEK_EOF",
            )
            self._json(200, {"ok": code == 0, "path": rel, "output": text})
            return
        if write:
            self._json(400, {"error": "content required"})
            return
        code, text = STATE.engine.exec(
            cid,
            f"if [ -d {shell_quote(target)} ]; then ls -1 {shell_quote(target)}; "
            f"elif [ -f {shell_quote(target)} ]; then wc -c < {shell_quote(target)}; else echo missing; fi",
        )
        entries = []
        for line in text.splitlines():
            name = line.strip()
            if name and name != "missing":
                entries.append({"path": name, "kind": "dir" if not name.isdigit() else "file", "size": 0})
        self._json(200, {"path": rel, "entries": entries, "ok": code == 0})


def serve(host: str = "127.0.0.1", port: int = 7091) -> ThreadingHTTPServer:
    return ThreadingHTTPServer((host, port), Handler)


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    host = os.environ.get("SUPERVISOR_HOST", "127.0.0.1")
    port = int(os.environ.get("SUPERVISOR_PORT", "7091") or 7091)
    httpd = serve(host, port)
    log.info("supervisor listening on %s:%s", host, port)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        httpd.shutdown()
    return 0
