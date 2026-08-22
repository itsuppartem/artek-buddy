from __future__ import annotations

import base64
import re
from pathlib import Path
from typing import Any

from artek_buddy.consent import (
    CLASS_OWNER_EXEC,
    CLASS_OWNER_READ,
    CLASS_OWNER_WRITE,
    OWNER_HOME_SCOPE,
    owner_command_is_readonly,
)
from artek_buddy.runtime.tools.common import (
    _with_consent,
)


class OwnerToolsMixin:
    def _exec_read_owner_file(
        self, args: dict[str, Any], bound_bot_id: str | None
    ) -> dict[str, Any]:
        path = str(args.get("path") or "").strip()
        if not path:
            return {"ok": False, "error": "path is required"}
        bot_id, _run_id, _thread_id = self.runtime.resolve_turn_context(bound_bot_id)
        if not bot_id:
            return {"ok": False, "error": "no active bot"}
        job = {"path": path, "kind": "read"}
        data: bytes | None = None
        name = Path(path).name or "file"
        reader = getattr(self.runtime, "owner_file_reader", None)
        if callable(reader):
            try:
                raw = reader(path)
            except Exception as exc:
                return {"ok": False, "error": str(exc)}
            if isinstance(raw, tuple) and len(raw) == 2:
                name, data = (
                    str(raw[0]),
                    raw[1] if isinstance(raw[1], bytes) else str(raw[1]).encode(),
                )
            elif isinstance(raw, bytes):
                data = raw
            elif raw is not None:
                data = str(raw).encode()
        if data is None:
            found = self._owner_client_result(
                bot_id=bot_id,
                run_id=_run_id,
                action_class=CLASS_OWNER_READ,
                scope_key=OWNER_HOME_SCOPE,
                summary=f"Read {path} from your computer?",
                job=job,
            )
            if found and found.get("_data") is not None:
                name = str(found.get("name") or name)
                data = (
                    found["_data"]
                    if isinstance(found["_data"], bytes)
                    else str(found["_data"]).encode()
                )
            elif found and found.get("content_base64"):
                name = str(found.get("name") or name)
                data = base64.b64decode(found["content_base64"])
            elif found and found.get("text") is not None:
                name = str(found.get("name") or name)
                data = str(found["text"]).encode()
        if data is None:
            return {"ok": False, "error": "no paired client to read that file"}
        if len(data) > 1_000_000:
            return {"ok": False, "error": "file is larger than 1 MB"}
        dest_dir = Path(self.runtime.home_cwd(bot_id)) / "inbox"
        dest_dir.mkdir(parents=True, exist_ok=True)
        safe = re.sub(r"[^A-Za-z0-9._-]+", "_", name) or "file"
        dest = dest_dir / safe
        dest.write_bytes(data)
        return _with_consent({"ok": True, "path": str(dest), "name": safe, "bytes": len(data)})

    def _exec_write_owner_file(
        self, args: dict[str, Any], bound_bot_id: str | None
    ) -> dict[str, Any]:
        path = str(args.get("path") or "").strip()
        content = args.get("content")
        if not path:
            return {"ok": False, "error": "path is required"}
        if content is None:
            return {"ok": False, "error": "content is required"}
        text = content if isinstance(content, str) else str(content)
        if len(text.encode()) > 1_000_000:
            return {"ok": False, "error": "file is larger than 1 MB"}
        bot_id, run_id, _thread_id = self.runtime.resolve_turn_context(bound_bot_id)
        if not bot_id:
            return {"ok": False, "error": "no active bot"}
        job = {"path": path, "kind": "write", "text": text}
        denied = self._deny(
            bot_id,
            CLASS_OWNER_WRITE,
            OWNER_HOME_SCOPE,
            f"Write {path} on your computer?",
            detail=f"owner_write: {path}",
            path=path,
            job=job,
        )
        if denied:
            return denied
        writer = getattr(self.runtime, "owner_file_writer", None)
        if callable(writer):
            try:
                raw = writer(path, text)
            except Exception as exc:
                return {"ok": False, "error": str(exc)}
            if isinstance(raw, dict):
                return _with_consent(raw)
            return _with_consent({"ok": True, "path": path, "bytes": len(text.encode())})
        found = self._owner_client_result(
            bot_id=bot_id,
            run_id=run_id,
            action_class=CLASS_OWNER_WRITE,
            scope_key=OWNER_HOME_SCOPE,
            summary=f"Write {path} on your computer?",
            job=job,
        )
        if not found:
            return {"ok": False, "error": "no paired client to write that file"}
        if found.get("ok") is False:
            return {"ok": False, "error": str(found.get("error") or "write failed")}
        return _with_consent(
            {
                "ok": True,
                "path": str(found.get("path") or path),
                "bytes": found.get("bytes", len(text.encode())),
            }
        )

    def _exec_list_owner_dir(
        self, args: dict[str, Any], bound_bot_id: str | None
    ) -> dict[str, Any]:
        path = str(args.get("path") or "~").strip() or "~"
        bot_id, run_id, _thread_id = self.runtime.resolve_turn_context(bound_bot_id)
        if not bot_id:
            return {"ok": False, "error": "no active bot"}
        job = {"path": path, "kind": "list"}
        lister = getattr(self.runtime, "owner_dir_lister", None)
        if callable(lister):
            try:
                entries = lister(path)
            except Exception as exc:
                return {"ok": False, "error": str(exc)}
            return _with_consent({"ok": True, "path": path, "entries": entries})
        found = self._owner_client_result(
            bot_id=bot_id,
            run_id=run_id,
            action_class=CLASS_OWNER_READ,
            scope_key=OWNER_HOME_SCOPE,
            summary=f"List {path} on your computer?",
            job=job,
        )
        if not found:
            return {"ok": False, "error": "no paired client to list that folder"}
        if found.get("ok") is False:
            return {"ok": False, "error": str(found.get("error") or "list failed")}
        return _with_consent(
            {
                "ok": True,
                "path": str(found.get("path") or path),
                "entries": found.get("entries") or [],
            }
        )

    def _exec_run_owner_command(
        self, args: dict[str, Any], bound_bot_id: str | None
    ) -> dict[str, Any]:
        command = str(args.get("command") or "").strip()
        cwd = str(args.get("cwd") or "~").strip() or "~"
        if not command:
            return {"ok": False, "error": "command is required"}
        if len(command) > 8000:
            return {"ok": False, "error": "command is too long"}
        bot_id, run_id, _thread_id = self.runtime.resolve_turn_context(bound_bot_id)
        if not bot_id:
            return {"ok": False, "error": "no active bot"}
        job = {"command": command, "cwd": cwd, "kind": "exec"}
        if not owner_command_is_readonly(command):
            denied = self._deny(
                bot_id,
                CLASS_OWNER_EXEC,
                OWNER_HOME_SCOPE,
                f"Run `{command}` on your computer?",
                detail=f"owner_exec: {command}\ncwd: {cwd}",
                job=job,
            )
            if denied:
                return denied
        runner = getattr(self.runtime, "owner_command_runner", None)
        if callable(runner):
            try:
                raw = runner(command, cwd)
            except Exception as exc:
                return {"ok": False, "error": str(exc)}
            if isinstance(raw, dict):
                return _with_consent(raw)
            return _with_consent({"ok": True, "stdout": str(raw), "stderr": "", "exit_code": 0})
        found = self._owner_client_result(
            bot_id=bot_id,
            run_id=run_id,
            action_class=CLASS_OWNER_EXEC,
            scope_key=OWNER_HOME_SCOPE,
            summary=f"Run `{command}` on your computer?",
            job=job,
        )
        if not found:
            return {"ok": False, "error": "no paired client to run that command"}
        if found.get("ok") is False and found.get("exit_code") is None:
            return {"ok": False, "error": str(found.get("error") or "command failed")}
        return _with_consent(
            {
                "ok": True,
                "stdout": str(found.get("stdout") or ""),
                "stderr": str(found.get("stderr") or ""),
                "exit_code": int(found.get("exit_code") or 0),
            }
        )
