from __future__ import annotations

import base64
import logging
import mimetypes
import shutil
from typing import Any

from pathlib import Path

from artek_buddy.consent import (
    CLASS_BROWSE,
    CLASS_OWNER_EXEC,
    CLASS_OWNER_READ,
    CLASS_OWNER_WRITE,
    CLASS_PAGE,
    OWNER_HOME_SCOPE,
    browse_origin,
    owner_command_is_readonly,
)
from artek_buddy.contracts.events import ProductEvent, ProductEventType
from artek_buddy.db.shaping import isoformat_utc, new_id
from artek_buddy.runtime.tools.common import (
    CONSENT_DONE,
    MAX_INLINE_FILE_BYTES,
    MAX_SEND_FILE_BYTES,
    PAGE_KINDS,
    _is_under,
    _playwright_browser_command,
    _safe_filename,
    _with_consent,
    emit_computer_event,
    format_owner_steer,
    log,
)
from artek_buddy.runtime.tools.specs import TOOL_SPECS, ToolSpec
from artek_buddy.runtime.tools.chat import ChatToolsMixin
from artek_buddy.runtime.tools.computer import ComputerToolsMixin
from artek_buddy.runtime.tools.owner import OwnerToolsMixin
from artek_buddy.runtime.tools.subagents import SubagentToolsMixin


class ProductToolsCore:
    def __init__(self, runtime: Any) -> None:
        self.runtime = runtime

    def specs(self, role: str = "lead") -> list[ToolSpec]:
        if role == "subagent":
            return [spec for spec in TOOL_SPECS if not spec.lead_only]
        return list(TOOL_SPECS)

    def names(self, role: str = "lead") -> list[str]:
        return [spec.name for spec in self.specs(role)]

    def _deny(
        self,
        bot_id: str | None,
        action_class: str,
        scope_key: str,
        summary: str,
        *,
        detail: str | None = None,
        path: str | None = None,
        job: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        hub = getattr(self.runtime, "consent", None)
        if hub is None:
            return None
        resolved_bot, run_id, _thread_id = self.runtime.resolve_turn_context(bot_id)
        device_id = getattr(self.runtime, "resolve_turn_device", lambda: None)()
        if not resolved_bot:
            return {"ok": False, "error": "no active bot"}
        allowed = hub.require(
            bot_id=resolved_bot,
            action_class=action_class,
            scope_key=scope_key,
            summary=summary,
            run_id=run_id,
            device_id=device_id,
            detail=detail,
            path=path,
            job=job,
        )
        if allowed:
            return None
        return {"ok": False, "error": "denied by owner", "denied": True}

    def _page_origin(self, actions: list[Any], extra: str | None = None) -> str | None:
        origin = browse_origin(extra or "")
        if origin:
            return origin
        for item in actions:
            if not isinstance(item, dict):
                continue
            origin = browse_origin(
                str(item.get("url") or item.get("path") or item.get("uri") or item.get("origin") or "")
            )
            if origin:
                return origin
        return None

    def _deny_page(self, bot_id: str | None, origin: str | None) -> dict[str, Any] | None:
        site = origin or "this page"
        return self._deny(
            bot_id,
            CLASS_PAGE,
            origin or "*",
            f"Fill, type, or click on {site} in the remote browser?",
            detail=f"page_input: {origin or '*'}",
        )

    def _owner_client_result(
        self,
        *,
        bot_id: str,
        run_id: str | None,
        action_class: str,
        scope_key: str,
        summary: str,
        job: dict[str, Any],
    ) -> dict[str, Any] | None:
        hub = getattr(self.runtime, "consent", None)
        if hub is None or getattr(hub, "_mode", lambda: None)() == "allow":
            return None
        request_id = getattr(hub, "last_request_id", None)
        if request_id:
            found = hub.take_owner_result(request_id)
            if found is not None:
                return found
            if action_class == CLASS_OWNER_READ and job.get("kind") != "list":
                file_found = hub.take_owner_file(request_id)
                if file_found is not None:
                    name, data = file_found
                    return {"ok": True, "name": name, "bytes": len(data), "_data": data}
            return None
        device_id = getattr(self.runtime, "resolve_turn_device", lambda: None)()
        return hub.pull_owner_action(
            bot_id=bot_id,
            action_class=action_class,
            scope_key=scope_key,
            summary=summary,
            job=job,
            run_id=run_id,
            device_id=device_id,
        )

    def execute(
        self,
        name: str,
        args: dict[str, Any] | None = None,
        bound_bot_id: str | None = None,
    ) -> dict[str, Any]:
        handler = getattr(self, f"_exec_{name}", None)
        if handler is None:
            return {"ok": False, "error": f"unknown tool: {name}"}
        result = handler(args or {}, bound_bot_id)
        if not isinstance(result, dict):
            return result
        steer = self._take_owner_steer(bound_bot_id)
        if steer:
            result = {**result, **steer}
        return result

    def _take_owner_steer(self, bound_bot_id: str | None) -> dict[str, Any] | None:
        store = getattr(self.runtime, "store", None)
        drain = getattr(store, "drain_inbox", None)
        if not callable(drain):
            return None
        bot_id, _run_id, _thread_id = self.runtime.resolve_turn_context(bound_bot_id)
        if not bot_id:
            return None
        try:
            items = drain(bot_id)
        except Exception:
            log.exception("failed to drain mid-turn owner message")
            return None
        return format_owner_steer(items or [])


class ProductTools(
    ChatToolsMixin,
    OwnerToolsMixin,
    ComputerToolsMixin,
    SubagentToolsMixin,
    ProductToolsCore,
):
    pass
