from __future__ import annotations

import time
from typing import Any

from artek_buddy.consent import (
    CLASS_OWNER_READ,
    CLASS_PAGE,
    browse_origin,
)
from artek_buddy.observe import log_tool
from artek_buddy.runtime.tools.apps import AppsToolsMixin
from artek_buddy.runtime.tools.books import BooksToolsMixin
from artek_buddy.runtime.tools.chat import ChatToolsMixin
from artek_buddy.runtime.tools.common import (
    format_owner_steer,
    log,
)
from artek_buddy.runtime.tools.computer import ComputerToolsMixin
from artek_buddy.runtime.tools.owner import OwnerToolsMixin
from artek_buddy.runtime.tools.specs import TOOL_SPECS, ToolSpec
from artek_buddy.runtime.tools.subagents import SubagentToolsMixin
from artek_buddy.runtime.types import TurnContext
from artek_buddy.runtime.worker_activity import touch_worker_activity

WORKER_ONLY_TOOLS = frozenset(
    {
        "send_file",
        "read_owner_file",
        "write_owner_file",
        "list_owner_dir",
        "run_owner_command",
        "open_path",
        "launch_app",
        "close_app",
        "computer_observe",
        "computer_act",
        "browser_act",
        "report_progress",
    }
)
LEAD_FORBIDDEN_OWNER_TOOLS = frozenset(
    {
        "read_owner_file",
        "write_owner_file",
        "list_owner_dir",
        "run_owner_command",
    }
)


class ProductToolsCore:
    def __init__(self, runtime: Any) -> None:
        self.runtime = runtime

    def specs(self, role: str = "lead") -> list[ToolSpec]:
        extra = self._connected_specs()
        if role == "subagent":
            return [spec for spec in TOOL_SPECS if not spec.lead_only] + extra
        return [spec for spec in TOOL_SPECS if spec.name not in WORKER_ONLY_TOOLS] + extra

    def _connected_specs(self) -> list[ToolSpec]:
        store = getattr(self.runtime, "store", None)
        settings = getattr(self.runtime, "settings", None)
        if store is None or settings is None or not store.raw_connection_key():
            return []
        slugs = list(store.connected_slugs())
        if not slugs:
            return []
        from artek_buddy.runtime.factory import runtime_kind

        if runtime_kind(settings) == "scripted":
            from artek_buddy.connections.broker import fake_broker

            broker = fake_broker()
            broker.hydrate(slugs)
            return broker.tool_specs(slugs)
        from artek_buddy.connections.http import HttpBroker

        return HttpBroker(store.raw_connection_key() or "").tool_specs(slugs)

    def _run_connected_tool(
        self, name: str, args: dict[str, Any], bound_bot_id: str | None
    ) -> dict[str, Any]:
        store = getattr(self.runtime, "store", None)
        settings = getattr(self.runtime, "settings", None)
        if store is None or settings is None:
            return {"ok": False, "error": "app is not connected"}
        row = store.connection_for_tool(name)
        if row is None:
            return {"ok": False, "error": "app is not connected"}
        remote_id = store.connection_remote_id(row.id)
        key = store.raw_connection_key() or ""
        from artek_buddy.runtime.factory import runtime_kind

        if runtime_kind(settings) == "scripted":
            from artek_buddy.connections.broker import fake_broker

            broker = fake_broker()
            broker.hydrate([row.provider])
        else:
            from artek_buddy.connections.http import HttpBroker

            broker = HttpBroker(key)
        result = broker.execute(name, args, provider=row.provider, remote_id=remote_id, key=key)
        text = str(result.get("text") or "").strip() if isinstance(result, dict) else ""
        if isinstance(result, dict) and result.get("ok") and text:
            self._append_bot_blocks(
                args or {},
                bound_bot_id,
                [{"kind": "plugin", "name": row.display_name, "text": text[:800]}],
                mark_sent=False,
            )
        return result

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
        allowed, _request_id = self._consent_gate(
            bot_id,
            action_class,
            scope_key,
            summary,
            detail=detail,
            path=path,
            job=job,
        )
        if allowed:
            return None
        return {"ok": False, "error": "denied by owner", "denied": True}

    def _consent_gate(
        self,
        bot_id: str | None,
        action_class: str,
        scope_key: str,
        summary: str,
        *,
        detail: str | None = None,
        path: str | None = None,
        job: dict[str, Any] | None = None,
    ) -> tuple[bool, str | None]:
        hub = getattr(self.runtime, "consent", None)
        if hub is None:
            return True, None
        resolved_bot, run_id, _thread_id = self.runtime.resolve_turn_context(bot_id)
        device_id = getattr(self.runtime, "resolve_turn_device", lambda: None)()
        if not resolved_bot:
            return False, None
        return hub.require(
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

    def _page_origin(self, actions: list[Any], extra: str | None = None) -> str | None:
        origin = browse_origin(extra or "")
        if origin:
            return origin
        for item in actions:
            if not isinstance(item, dict):
                continue
            origin = browse_origin(
                str(
                    item.get("url")
                    or item.get("path")
                    or item.get("uri")
                    or item.get("origin")
                    or ""
                )
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
        request_id: str | None = None,
    ) -> dict[str, Any] | None:
        hub = getattr(self.runtime, "consent", None)
        if hub is None or getattr(hub, "_mode", lambda: None)() == "allow":
            return None
        if request_id:
            found = hub.take_owner_result(request_id, finalize_timeout=False)
            if found is not None:
                return found
            if action_class == CLASS_OWNER_READ and job.get("kind") != "list":
                file_found = hub.take_owner_file(request_id, finalize_timeout=False)
                if file_found is not None:
                    name, data = file_found
                    return {"ok": True, "name": name, "bytes": len(data), "_data": data}
            hub.timeout_owner_job(request_id)
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
        turn: TurnContext | None = None,
    ) -> dict[str, Any]:
        started = time.monotonic()
        result: dict[str, Any] | None = None
        ctx = turn or self._resolve_turn(bound_bot_id)
        if ctx is None:
            return {"ok": False, "error": "no turn context"}
        apply = getattr(self.runtime, "apply_callback_context", None)
        reset = getattr(self.runtime, "reset_callback_context", None)
        tokens = apply(ctx) if callable(apply) else None
        activity_started = False
        try:
            if self._turn_cancelled(ctx):
                if ctx.role == "subagent":
                    return {"ok": False, "error": "worker was cancelled"}
                return {"ok": False, "error": "turn was cancelled"}
            if ctx.role != "subagent" and name == "report_progress":
                return {"ok": False, "error": "lead cannot use report_progress"}
            if ctx.role != "subagent" and name in LEAD_FORBIDDEN_OWNER_TOOLS:
                return {
                    "ok": False,
                    "error": f"lead cannot use {name}; spawn_subagent for This-PC work",
                }
            blocked = self._block_status_replace(name, ctx)
            if blocked is not None:
                return blocked
            if ctx.role == "subagent" and name != "report_progress":
                touch_worker_activity(
                    self.runtime,
                    ctx.run_id,
                    kind="tool_started",
                    tool_name=name,
                    tool_running=True,
                )
                activity_started = True
            handler = getattr(self, f"_exec_{name}", None)
            if handler is None:
                result = self._run_connected_tool(name, args or {}, bound_bot_id or ctx.bot_id)
                return result
            result = handler(args or {}, bound_bot_id or ctx.bot_id)
            if not isinstance(result, dict):
                return result
            if ctx.role == "subagent":
                note = self._take_worker_clarification(bound_bot_id or ctx.bot_id)
                if note:
                    result = {**result, **note}
                return result
            steer = self._take_owner_steer(bound_bot_id or ctx.bot_id)
            if steer:
                result = {**result, **steer}
            return result
        finally:
            if activity_started:
                touch_worker_activity(
                    self.runtime,
                    ctx.run_id,
                    kind="tool_finished",
                    tool_name=name,
                    tool_running=False,
                )
            runtime = getattr(getattr(self.runtime, "settings", None), "agent_runtime", None)
            log_tool(
                name,
                result if isinstance(result, dict) else None,
                latency_ms=int((time.monotonic() - started) * 1000),
                runtime=runtime,
                bot_id=ctx.bot_id,
                turn_id=ctx.run_id,
                thread_id=ctx.thread_id,
            )
            if tokens is not None and callable(reset):
                reset(tokens)

    def _resolve_turn(self, bound_bot_id: str | None) -> TurnContext | None:
        resolve = getattr(self.runtime, "resolve_turn", None)
        if callable(resolve):
            found = resolve(bound_bot_id)
            if found is not None:
                return found
        bot_id, run_id, thread_id = self.runtime.resolve_turn_context(bound_bot_id)
        if not bot_id or not run_id:
            return None
        role = self.runtime.resolve_turn_role(bound_bot_id)
        turn_role = role if role in {"lead", "subagent"} else "lead"
        return TurnContext(
            bot_id=bot_id,
            run_id=run_id,
            thread_id=thread_id or "",
            role=turn_role,
        )

    def _turn_cancelled(self, ctx: TurnContext) -> bool:
        check = getattr(self.runtime, "is_run_cancelled", None)
        if callable(check):
            try:
                if check(ctx.run_id):
                    return True
            except Exception:
                log.exception("failed to read run cancel state")
        if ctx.role == "subagent" and self._worker_cancelled(ctx.run_id):
            return True
        return False

    def _worker_cancelled(self, run_id: str) -> bool:
        service = getattr(self.runtime, "subagents", None)
        check = getattr(service, "is_cancelled", None) if service is not None else None
        if callable(check):
            try:
                return bool(check(run_id))
            except Exception:
                log.exception("failed to read worker cancel state")
                return False
        store = getattr(self.runtime, "store", None)
        getter = getattr(store, "get_subagent", None) if store is not None else None
        if not callable(getter):
            return False
        try:
            record = getter(run_id)
        except Exception:
            log.exception("failed to read worker row")
            return False
        return record is not None and record.status not in {"queued", "running"}

    def _block_status_replace(self, name: str, ctx: TurnContext) -> dict[str, Any] | None:
        if name not in {"stop_subagent", "restart_subagent"}:
            return None
        intent_for = getattr(self.runtime, "owner_intent_for", None)
        intent = intent_for(ctx.run_id) if callable(intent_for) else "other"
        if intent == "status":
            return {
                "ok": False,
                "error": "status-only message cannot stop or replace a worker",
            }
        if intent == "correction":
            return {
                "ok": False,
                "error": "use steer_subagent to correct a worker; do not replace it",
            }
        return None

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

    def _take_worker_clarification(self, bound_bot_id: str | None) -> dict[str, Any] | None:
        store = getattr(self.runtime, "store", None)
        take = getattr(store, "take_new_clarifications", None)
        if not callable(take):
            return None
        _bot_id, run_id, _thread_id = self.runtime.resolve_turn_context(bound_bot_id)
        if not run_id:
            return None
        try:
            note = take(run_id)
        except Exception:
            log.exception("failed to drain worker clarification")
            return None
        if not note:
            return None
        return {
            "lead_clarification": note,
            "owner_instruction": (
                "The lead sent a correction. Apply it after this tool. "
                "Do not restart the current side effect."
            ),
        }


class ProductTools(
    ChatToolsMixin,
    BooksToolsMixin,
    AppsToolsMixin,
    OwnerToolsMixin,
    ComputerToolsMixin,
    SubagentToolsMixin,
    ProductToolsCore,
):
    pass
