from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlencode


@dataclass
class SandboxBox:
    id: str
    view_port: int | None
    control_port: int | None
    screen_url: str | None
    running: bool = True
    ok: bool = True


class SupervisorClient:
    def __init__(self, base: str, token: str, timeout: float = 60) -> None:
        self.base = base.rstrip("/")
        self.token = token
        self.timeout = timeout

    def _request(
        self,
        method: str,
        path: str,
        body: dict[str, Any] | None = None,
        bot_id: str | None = None,
    ) -> dict[str, Any]:
        data = None
        headers = {"Accept": "application/json", "Authorization": f"Bearer {self.token}"}
        if bot_id:
            headers["x-artek-bot-id"] = bot_id
        if body is not None:
            data = json.dumps(body).encode("utf-8")
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(
            f"{self.base}{path}",
            data=data,
            method=method,
            headers=headers,
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as resp:
                raw = resp.read()
                return json.loads(raw.decode("utf-8") or "{}") if raw else {}
        except urllib.error.HTTPError as err:
            detail = err.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"supervisor {err.code}: {detail}") from err

    def provision(self, bot_id: str, home_key: str) -> SandboxBox:
        payload = self._request("POST", "/computers", {"bot_id": bot_id, "home_key": home_key})
        return _box(payload)

    def inspect(self, provider_ref: str) -> SandboxBox:
        return _box(self._request("GET", f"/computers/{provider_ref}"))

    def stop(self, provider_ref: str) -> None:
        self._request("POST", f"/computers/{provider_ref}/stop", {})

    def destroy(self, provider_ref: str) -> None:
        self._request("DELETE", f"/computers/{provider_ref}")

    def screen_mode(self, provider_ref: str, interactive: bool, control_token: str | None) -> SandboxBox:
        return _box(
            self._request(
                "POST",
                f"/computers/{provider_ref}/screen-mode",
                {"interactive": interactive, "control_token": control_token},
            )
        )

    def observe(self, provider_ref: str) -> dict[str, Any]:
        return self._request("POST", f"/computers/{provider_ref}/observe", {})

    def act(self, provider_ref: str, actions: list[dict[str, Any]]) -> dict[str, Any]:
        return self._request("POST", f"/computers/{provider_ref}/actions", {"actions": actions})

    def execute(self, provider_ref: str, command: str) -> dict[str, Any]:
        return self._request("POST", f"/computers/{provider_ref}/exec", {"command": command})

    def send_input(self, provider_ref: str, kind: str, payload: dict[str, Any]) -> dict[str, Any]:
        return self._request(
            "POST",
            f"/computers/{provider_ref}/input",
            {"kind": kind, "payload": payload},
        )

    def list_files(self, provider_ref: str, path: str = "/") -> dict[str, Any]:
        query = urlencode({"path": path})
        return self._request("GET", f"/computers/{provider_ref}/files?{query}")

    def write_file(self, provider_ref: str, path: str, content: str) -> dict[str, Any]:
        return self._request(
            "POST",
            f"/computers/{provider_ref}/files",
            {"path": path, "content": content},
        )


class FakeSupervisorClient:
    def __init__(self) -> None:
        self.boxes: dict[str, dict[str, Any]] = {}
        self.calls: list[tuple[str, Any]] = []

    def provision(self, bot_id: str, home_key: str) -> SandboxBox:
        cid = f"fake-{home_key}"
        self.boxes[cid] = {
            "id": cid,
            "bot_id": bot_id,
            "home_key": home_key,
            "running": True,
            "interactive": False,
            "control_token": None,
            "files": {},
        }
        self.calls.append(("provision", home_key))
        return SandboxBox(cid, None, None, None, True, True)

    def inspect(self, provider_ref: str) -> SandboxBox:
        box = self.boxes.get(provider_ref)
        if box is None:
            raise RuntimeError("not found")
        return SandboxBox(
            provider_ref,
            None,
            None,
            None,
            bool(box.get("running", True)),
            True,
        )

    def stop(self, provider_ref: str) -> None:
        if provider_ref in self.boxes:
            self.boxes[provider_ref]["running"] = False
        self.calls.append(("stop", provider_ref))

    def destroy(self, provider_ref: str) -> None:
        self.boxes.pop(provider_ref, None)
        self.calls.append(("destroy", provider_ref))

    def screen_mode(self, provider_ref: str, interactive: bool, control_token: str | None) -> SandboxBox:
        if provider_ref not in self.boxes:
            raise RuntimeError("not found")
        box = self.boxes[provider_ref]
        box["interactive"] = interactive
        box["control_token"] = control_token
        self.calls.append(("screen_mode", interactive, control_token))
        return self.inspect(provider_ref)

    def observe(self, provider_ref: str) -> dict[str, Any]:
        self.calls.append(("observe", provider_ref))
        return {"ok": True, "output": "GEOM 1280 800\nCURSOR X=10 Y=10", "image_png_base64": ""}

    def act(self, provider_ref: str, actions: list[dict[str, Any]]) -> dict[str, Any]:
        self.calls.append(("act", actions))
        return {"ok": True, "output": "ok"}

    def execute(self, provider_ref: str, command: str) -> dict[str, Any]:
        self.calls.append(("exec", command))
        return {"ok": True, "exit_code": 0, "output": ""}

    def send_input(self, provider_ref: str, kind: str, payload: dict[str, Any]) -> dict[str, Any]:
        self.calls.append(("input", kind, payload))
        return {"ok": True}

    def list_files(self, provider_ref: str, path: str = "/") -> dict[str, Any]:
        files = (self.boxes.get(provider_ref) or {}).get("files") or {}
        return {"path": path, "entries": [{"path": name, "kind": "file", "size": len(content)} for name, content in files.items()]}

    def write_file(self, provider_ref: str, path: str, content: str) -> dict[str, Any]:
        box = self.boxes.setdefault(provider_ref, {"files": {}})
        box.setdefault("files", {})[path] = content
        return {"ok": True, "path": path}


def _box(payload: dict[str, Any]) -> SandboxBox:
    return SandboxBox(
        id=str(payload.get("id") or ""),
        view_port=payload.get("view_port"),
        control_port=payload.get("control_port"),
        screen_url=payload.get("screen_url"),
        running=bool(payload.get("running", True)),
        ok=bool(payload.get("ok", True)),
    )
