from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from artek_buddy.contracts.events import ProductEvent, ProductEventType
from artek_buddy.db.shaping import isoformat_utc, new_id

log = logging.getLogger("artek_buddy")


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    input_schema: dict[str, Any]
    lead_only: bool = False


def emit_computer_event(events: Any, bot: Any, status: Any) -> None:
    try:
        events.publish(
            ProductEvent(
                id=new_id("evt"),
                workspace_id=bot.workspace_id,
                thread_id=bot.thread_id,
                bot_id=bot.id,
                seq=events.next_seq(bot.id),
                type=ProductEventType.THREAD_COMPUTER,
                created_at=isoformat_utc(),
                payload=status.model_dump(mode="json"),
            )
        )
    except Exception:
        log.exception("failed to emit computer event")


TOOL_SPECS: tuple[ToolSpec, ...] = (
    ToolSpec(
        name="send_message",
        description=(
            "Post a message to the user in this chat immediately. "
            "Use this whenever you have an update, explanation, intermediate result, "
            "or decision point as soon as it is ready."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "text": {
                    "type": "string",
                    "description": "Message text to send to the user (supports markdown).",
                },
                "options": {
                    "type": "array",
                    "description": "Optional multiple choice option buttons for the user to pick from.",
                    "items": {"type": "string"},
                },
            },
            "required": ["text"],
        },
    ),
    ToolSpec(
        name="ask_user",
        description=(
            "Ask the user a question with interactive multiple choice buttons. "
            "The user will be able to click an option to reply immediately."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "question": {
                    "type": "string",
                    "description": "The question to ask.",
                },
                "detail": {
                    "type": "string",
                    "description": "Optional description or context under the question.",
                },
                "options": {
                    "type": "array",
                    "description": "List of choice options (e.g. ['A — option 1', 'B — option 2']).",
                    "items": {"type": "string"},
                },
            },
            "required": ["question", "options"],
        },
    ),
    ToolSpec(
        name="remember",
        description="Store a durable fact or key preference in this bot's explicit memory for future turns.",
        input_schema={
            "type": "object",
            "properties": {
                "content": {
                    "type": "string",
                    "description": "The fact or key piece of information to remember.",
                },
                "path": {
                    "type": "string",
                    "description": "Path to the memory file (default: MEMORY.md).",
                },
            },
            "required": ["content"],
        },
    ),
    ToolSpec(
        name="open_path",
        description=(
            "Open a URL (e.g. 'https://youtube.com') or workspace file in its default "
            "graphical application on this bot's desktop screen. Fast and direct."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "URL (http/https) or file path to open on screen.",
                }
            },
            "required": ["path"],
        },
    ),
    ToolSpec(
        name="launch_app",
        description=(
            "Launch an installed graphical application on this bot's desktop "
            "(e.g. 'chromium', 'google-chrome', 'terminal'), optionally with a URI/URL."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "application": {
                    "type": "string",
                    "description": "Application name or binary to launch.",
                },
                "uri": {
                    "type": "string",
                    "description": "Optional URI or URL to open with the application.",
                },
            },
            "required": ["application"],
        },
    ),
    ToolSpec(
        name="close_app",
        description=(
            "Close a graphical application on this bot's desktop immediately "
            "(e.g. 'chromium' / 'browser' to close the on-screen Chromium). "
            "Use this instead of clicking the window close button."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "application": {
                    "type": "string",
                    "description": "Application name to close (chromium, browser, or a binary name).",
                },
            },
            "required": ["application"],
        },
    ),
    ToolSpec(
        name="computer_observe",
        description="Look at this bot's Linux desktop: screenshot metadata, cursor, and the active window.",
        input_schema={"type": "object", "properties": {}, "additionalProperties": False},
    ),
    ToolSpec(
        name="computer_act",
        description="Send mouse, keyboard, or launch actions to this bot's Linux desktop.",
        input_schema={
            "type": "object",
            "properties": {
                "actions": {
                    "type": "array",
                    "description": "Ordered desktop actions (click, move, type, key, scroll, wait, open, launch, close).",
                    "items": {"type": "object"},
                }
            },
            "required": ["actions"],
        },
    ),
    ToolSpec(
        name="request_takeover",
        description="Pause this turn and ask the human to take control of the desktop.",
        input_schema={"type": "object", "properties": {}, "additionalProperties": False},
        lead_only=True,
    ),
    ToolSpec(
        name="spawn_subagent",
        description="Start a worker on this chat's desktop for one task. Returns immediately with an index.",
        input_schema={
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Short worker name."},
                "task": {"type": "string", "description": "What the worker should do."},
            },
            "required": ["task"],
        },
        lead_only=True,
    ),
    ToolSpec(
        name="list_subagents",
        description="List this chat's workers and their status.",
        input_schema={"type": "object", "properties": {}, "additionalProperties": False},
        lead_only=True,
    ),
    ToolSpec(
        name="inspect_subagent",
        description="Read a worker's reasoning, stage, and result. ref is the index, name, or id.",
        input_schema={
            "type": "object",
            "properties": {
                "ref": {
                    "type": "string",
                    "description": "Subagent index (2), name, or id.",
                }
            },
            "required": ["ref"],
        },
        lead_only=True,
    ),
    ToolSpec(
        name="stop_subagent",
        description="Stop a running worker.",
        input_schema={
            "type": "object",
            "properties": {"ref": {"type": "string"}},
            "required": ["ref"],
        },
        lead_only=True,
    ),
    ToolSpec(
        name="restart_subagent",
        description="Stop a worker if needed and run the same task again.",
        input_schema={
            "type": "object",
            "properties": {"ref": {"type": "string"}},
            "required": ["ref"],
        },
        lead_only=True,
    ),
    ToolSpec(
        name="steer_subagent",
        description=(
            "Give a worker extra instructions while it works. "
            "ref is the index, name, or id. The worker continues the same task."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "ref": {
                    "type": "string",
                    "description": "Subagent index (2), name, or id.",
                },
                "text": {
                    "type": "string",
                    "description": "The correction or extra instruction.",
                },
            },
            "required": ["ref", "text"],
        },
        lead_only=True,
    ),
)


class ProductTools:
    def __init__(self, runtime: Any) -> None:
        self.runtime = runtime

    def specs(self, role: str = "lead") -> list[ToolSpec]:
        if role == "subagent":
            return [spec for spec in TOOL_SPECS if not spec.lead_only]
        return list(TOOL_SPECS)

    def names(self, role: str = "lead") -> list[str]:
        return [spec.name for spec in self.specs(role)]

    def execute(
        self,
        name: str,
        args: dict[str, Any] | None = None,
        bound_bot_id: str | None = None,
    ) -> dict[str, Any]:
        handler = getattr(self, f"_exec_{name}", None)
        if handler is None:
            return {"ok": False, "error": f"unknown tool: {name}"}
        return handler(args or {}, bound_bot_id)

    def _exec_remember(self, args: dict[str, Any], bound_bot_id: str | None) -> dict[str, Any]:
        content = str(args.get("content") or "").strip()
        path = str(args.get("path") or "MEMORY.md").strip() or "MEMORY.md"
        if not content:
            return {"ok": False, "error": "content cannot be empty"}
        bot_id, run_id, thread_id = self.runtime.resolve_turn_context(bound_bot_id)
        if self.runtime.store is not None:
            try:
                doc = self.runtime.store.save_memory(
                    scope="bot" if bot_id else "user",
                    path=path,
                    content=content,
                    bot_id=bot_id,
                    source_run_id=run_id,
                    source_thread_id=thread_id,
                )
                return {
                    "ok": True,
                    "document_id": doc.id,
                    "revision": doc.revision,
                    "path": doc.path,
                    "scope": doc.scope.value if hasattr(doc.scope, "value") else str(doc.scope),
                }
            except Exception as exc:
                log.exception("failed to save memory in remember tool")
                return {"ok": False, "error": str(exc)}
        return {"ok": True, "saved": False}

    def _require_computer(
        self, bound_bot_id: str | None
    ) -> tuple[Any, Any] | dict[str, Any]:
        bot_id, _run_id, _thread_id = self.runtime.resolve_turn_context(bound_bot_id)
        if self.runtime.computers is None or self.runtime.store is None or not bot_id:
            return {"ok": False, "error": "computer is not available"}
        bot = self.runtime.store.get_bot(bot_id)
        if bot is None:
            return {"ok": False, "error": "bot not found"}
        return bot, bot_id

    def _exec_computer_observe(self, args: dict[str, Any], bound_bot_id: str | None) -> dict[str, Any]:
        found = self._require_computer(bound_bot_id)
        if isinstance(found, dict):
            return found
        bot, _bot_id = found
        try:
            return self.runtime.computers.observe(bot)
        except Exception as exc:
            log.exception("computer_observe failed")
            return {"ok": False, "error": str(exc)}

    def _exec_computer_act(self, args: dict[str, Any], bound_bot_id: str | None) -> dict[str, Any]:
        found = self._require_computer(bound_bot_id)
        if isinstance(found, dict):
            return found
        bot, _bot_id = found
        actions = args.get("actions")
        if not isinstance(actions, list) or not actions:
            return {"ok": False, "error": "actions must be a non-empty list"}
        try:
            return self.runtime.computers.act(bot, actions)
        except Exception as exc:
            log.exception("computer_act failed")
            return {"ok": False, "error": str(exc)}

    def _exec_open_path(self, args: dict[str, Any], bound_bot_id: str | None) -> dict[str, Any]:
        found = self._require_computer(bound_bot_id)
        if isinstance(found, dict):
            return found
        bot, _bot_id = found
        path = str(args.get("path") or args.get("url") or "").strip()
        if not path:
            return {"ok": False, "error": "path is required"}
        try:
            res = self.runtime.computers.open_path(bot, path)
            if self.runtime.events is not None:
                emit_computer_event(self.runtime.events, bot, self.runtime.computers.status(bot))
            return res
        except Exception as exc:
            log.exception("open_path failed")
            return {"ok": False, "error": str(exc)}

    def _exec_launch_app(self, args: dict[str, Any], bound_bot_id: str | None) -> dict[str, Any]:
        found = self._require_computer(bound_bot_id)
        if isinstance(found, dict):
            return found
        bot, _bot_id = found
        app_name = str(args.get("application") or args.get("name") or "").strip()
        if not app_name:
            return {"ok": False, "error": "application name is required"}
        uri = str(args.get("uri") or "").strip() or None
        try:
            res = self.runtime.computers.launch_app(bot, app_name, uri=uri)
            if self.runtime.events is not None:
                emit_computer_event(self.runtime.events, bot, self.runtime.computers.status(bot))
            return res
        except Exception as exc:
            log.exception("launch_app failed")
            return {"ok": False, "error": str(exc)}

    def _exec_close_app(self, args: dict[str, Any], bound_bot_id: str | None) -> dict[str, Any]:
        found = self._require_computer(bound_bot_id)
        if isinstance(found, dict):
            return found
        bot, _bot_id = found
        app_name = str(args.get("application") or args.get("name") or "").strip()
        if not app_name:
            return {"ok": False, "error": "application name is required"}
        try:
            res = self.runtime.computers.close_app(bot, app_name)
            if self.runtime.events is not None:
                emit_computer_event(self.runtime.events, bot, self.runtime.computers.status(bot))
            return res
        except Exception as exc:
            log.exception("close_app failed")
            return {"ok": False, "error": str(exc)}

    def _exec_request_takeover(self, args: dict[str, Any], bound_bot_id: str | None) -> dict[str, Any]:
        bot_id, run_id, _thread_id = self.runtime.resolve_turn_context(bound_bot_id)
        if self.runtime.store is None or not bot_id or not run_id:
            return {"ok": False, "error": "no active run"}
        try:
            self.runtime.store.mark_run_waiting_takeover(run_id)
        except Exception as exc:
            log.exception("failed to mark waiting_takeover")
            return {"ok": False, "error": str(exc)}
        if self.runtime.on_takeover_requested:
            try:
                self.runtime.on_takeover_requested(bot_id, run_id)
            except Exception:
                log.exception("takeover callback failed")
        return {"ok": True, "waiting": True}

    def _require_subagents(
        self, bound_bot_id: str | None
    ) -> tuple[Any, Any] | dict[str, Any]:
        bot_id, run_id, _thread_id = self.runtime.resolve_turn_context(bound_bot_id)
        if self.runtime.subagents is None or self.runtime.store is None or not bot_id:
            return {"ok": False, "error": "subagents are not available"}
        bot = self.runtime.store.get_bot(bot_id)
        if bot is None:
            return {"ok": False, "error": "bot not found"}
        return bot, run_id

    def _exec_spawn_subagent(self, args: dict[str, Any], bound_bot_id: str | None) -> dict[str, Any]:
        found = self._require_subagents(bound_bot_id)
        if isinstance(found, dict):
            return found
        bot, run_id = found
        try:
            record = self.runtime.subagents.spawn(
                bot,
                str(args.get("name") or ""),
                str(args.get("task") or ""),
                parent_run_id=run_id,
            )
        except Exception as exc:
            return {"ok": False, "error": str(exc)}
        return {
            "ok": True,
            "subagent_id": record.id,
            "index": record.index,
            "name": record.name,
            "status": record.status,
        }

    def _exec_list_subagents(self, args: dict[str, Any], bound_bot_id: str | None) -> dict[str, Any]:
        found = self._require_subagents(bound_bot_id)
        if isinstance(found, dict):
            return found
        bot, _run_id = found
        rows = self.runtime.subagents.list_for(bot)
        return {
            "ok": True,
            "subagents": [
                {
                    "id": item.id,
                    "index": item.index,
                    "name": item.name,
                    "task": item.task,
                    "status": item.status,
                    "progress": item.progress,
                    "thinking": item.thinking,
                    "clarifications": item.clarifications,
                }
                for item in rows
            ],
        }

    def _exec_inspect_subagent(self, args: dict[str, Any], bound_bot_id: str | None) -> dict[str, Any]:
        found = self._require_subagents(bound_bot_id)
        if isinstance(found, dict):
            return found
        bot, _run_id = found
        ref = str(args.get("ref") or args.get("id") or args.get("index") or "").strip()
        if not ref:
            return {"ok": False, "error": "ref is required (index, name, or id)"}
        try:
            item = self.runtime.subagents.inspect(bot, ref)
        except Exception as exc:
            return {"ok": False, "error": str(exc)}
        return {
            "ok": True,
            "id": item.id,
            "index": item.index,
            "name": item.name,
            "task": item.task,
            "status": item.status,
            "progress": item.progress,
            "thinking": item.thinking,
            "result": item.result,
            "error": item.error,
            "clarifications": item.clarifications,
        }

    def _exec_stop_subagent(self, args: dict[str, Any], bound_bot_id: str | None) -> dict[str, Any]:
        found = self._require_subagents(bound_bot_id)
        if isinstance(found, dict):
            return found
        bot, _run_id = found
        ref = str(args.get("ref") or args.get("id") or args.get("index") or "").strip()
        if not ref:
            return {"ok": False, "error": "ref is required"}
        try:
            item = self.runtime.subagents.stop(bot, ref)
        except Exception as exc:
            return {"ok": False, "error": str(exc)}
        return {"ok": True, "id": item.id, "index": item.index, "status": item.status}

    def _exec_restart_subagent(self, args: dict[str, Any], bound_bot_id: str | None) -> dict[str, Any]:
        found = self._require_subagents(bound_bot_id)
        if isinstance(found, dict):
            return found
        bot, _run_id = found
        ref = str(args.get("ref") or args.get("id") or args.get("index") or "").strip()
        if not ref:
            return {"ok": False, "error": "ref is required"}
        try:
            item = self.runtime.subagents.restart(bot, ref)
        except Exception as exc:
            return {"ok": False, "error": str(exc)}
        return {"ok": True, "id": item.id, "index": item.index, "status": item.status}

    def _exec_steer_subagent(self, args: dict[str, Any], bound_bot_id: str | None) -> dict[str, Any]:
        found = self._require_subagents(bound_bot_id)
        if isinstance(found, dict):
            return found
        bot, _run_id = found
        ref = str(args.get("ref") or args.get("id") or args.get("index") or "").strip()
        note = str(args.get("text") or args.get("note") or args.get("clarification") or "").strip()
        if not ref:
            return {"ok": False, "error": "ref is required"}
        if not note:
            return {"ok": False, "error": "text is required"}
        try:
            item = self.runtime.subagents.steer(bot, ref, note)
        except Exception as exc:
            return {"ok": False, "error": str(exc)}
        return {
            "ok": True,
            "id": item.id,
            "index": item.index,
            "status": item.status,
            "clarifications": item.clarifications,
        }

    def _append_bot_blocks(
        self,
        args: dict[str, Any],
        bound_bot_id: str | None,
        blocks: list[dict[str, Any]],
    ) -> dict[str, Any]:
        bot_id, run_id, _thread_id = self.runtime.resolve_turn_context(bound_bot_id)
        if self.runtime.store is None or not bot_id:
            return {"ok": False, "error": "store is not available"}
        bot = self.runtime.store.get_bot(bot_id)
        if bot is None:
            return {"ok": False, "error": "bot not found"}
        try:
            msg = self.runtime.store.append_bot_message(bot, blocks, run_id=run_id)
            self.runtime.mark_message_sent(run_id)
            if self.runtime.events is not None:
                event = ProductEvent(
                    id=new_id("evt"),
                    workspace_id=bot.workspace_id,
                    thread_id=bot.thread_id,
                    bot_id=bot.id,
                    seq=self.runtime.events.next_seq(bot.id),
                    type=ProductEventType.THREAD_MESSAGE_CREATED,
                    created_at=isoformat_utc(),
                    payload={"message": msg.model_dump(mode="json")},
                    run_id=run_id,
                )
                self.runtime.events.publish(event)
            return {"ok": True, "message_id": msg.id}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    def _exec_send_message(self, args: dict[str, Any], bound_bot_id: str | None) -> dict[str, Any]:
        text = str(args.get("text") or args.get("message") or "").strip()
        if not text:
            return {"ok": False, "error": "text is required"}
        raw_options = args.get("options")
        if isinstance(raw_options, list) and raw_options:
            actions = [{"id": f"opt_{i+1}", "label": str(opt)} for i, opt in enumerate(raw_options)]
            blocks = [
                {
                    "kind": "ask",
                    "text": text,
                    "detail": str(args.get("detail") or "").strip() or None,
                    "status": "pending",
                    "actions": actions,
                }
            ]
        else:
            blocks = [{"kind": "text", "text": text}]
        return self._append_bot_blocks(args, bound_bot_id, blocks)

    def _exec_ask_user(self, args: dict[str, Any], bound_bot_id: str | None) -> dict[str, Any]:
        question = str(args.get("question") or args.get("text") or "").strip()
        if not question:
            return {"ok": False, "error": "question is required"}
        raw_options = args.get("options") or []
        if not isinstance(raw_options, list) or not raw_options:
            return {"ok": False, "error": "options list is required"}
        actions = [{"id": f"opt_{i+1}", "label": str(opt)} for i, opt in enumerate(raw_options)]
        detail = str(args.get("detail") or "").strip() or None
        blocks = [
            {
                "kind": "ask",
                "text": question,
                "detail": detail,
                "status": "pending",
                "actions": actions,
            }
        ]
        return self._append_bot_blocks(args, bound_bot_id, blocks)
