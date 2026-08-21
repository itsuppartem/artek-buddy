from __future__ import annotations

import base64
import logging
import mimetypes
import re
import shutil
from dataclasses import dataclass
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

log = logging.getLogger("artek_buddy")

PAGE_KINDS = {"click", "type", "key", "down", "up", "scroll", "download", "fill", "submit", "press"}
MAX_SEND_FILE_BYTES = 25 * 1024 * 1024
MAX_INLINE_FILE_BYTES = 1 * 1024 * 1024
CONSENT_DONE = "The owner already answered the Allow card. Do not ask them to press Allow."
OWNER_STEER = (
    "The owner sent this while you were working. Apply it now. "
    "Do not finish the old plan first. Do not wait until this turn ends."
)


def format_owner_steer(items: list[dict[str, str | None]]) -> dict[str, Any] | None:
    texts = [str(item.get("text") or "").strip() for item in items]
    texts = [text for text in texts if text]
    if not texts:
        return None
    lines = [OWNER_STEER]
    for index, text in enumerate(texts, start=1):
        lines.append(f"{index}. {text}")
    return {"owner_follow_up": texts, "owner_instruction": "\n".join(lines)}


def _with_consent(payload: dict[str, Any]) -> dict[str, Any]:
    if payload.get("denied") or payload.get("ok") is False:
        return payload
    out = dict(payload)
    out.setdefault("consent", "allowed")
    out.setdefault("note", CONSENT_DONE)
    return out


def _safe_filename(name: str) -> str:
    base = Path(str(name or "").strip()).name.replace("\x00", "").strip()
    return (base or "file")[:200]


def _is_under(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def _playwright_browser_command(actions: list[Any]) -> str:
    import json

    steps = []
    for item in actions:
        if isinstance(item, dict):
            steps.append(
                {
                    "kind": str(item.get("kind") or ""),
                    "url": str(item.get("url") or item.get("path") or ""),
                    "selector": str(item.get("selector") or ""),
                    "text": str(item.get("text") or ""),
                    "key": str(item.get("key") or ""),
                }
            )
    payload = json.dumps(steps)
    return (
        "python3 - <<'PY'\n"
        "import json, sys\n"
        "from playwright.sync_api import sync_playwright\n"
        f"STEPS = json.loads({payload!r})\n"
        "with sync_playwright() as p:\n"
        "    browser = p.chromium.connect_over_cdp('http://127.0.0.1:9222')\n"
        "    context = browser.contexts[0] if browser.contexts else browser.new_context()\n"
        "    page = context.pages[0] if context.pages else context.new_page()\n"
        "    for step in STEPS:\n"
        "        kind = step.get('kind')\n"
        "        if kind == 'goto' and step.get('url'):\n"
        "            page.goto(step['url'], wait_until='domcontentloaded')\n"
        "        elif kind == 'fill' and step.get('selector'):\n"
        "            page.fill(step['selector'], step.get('text') or '')\n"
        "        elif kind == 'click' and step.get('selector'):\n"
        "            page.click(step['selector'])\n"
        "        elif kind == 'type':\n"
        "            page.keyboard.type(step.get('text') or '')\n"
        "        elif kind == 'press':\n"
        "            page.keyboard.press(step.get('key') or 'Enter')\n"
        "        elif kind == 'submit':\n"
        "            sel = step.get('selector')\n"
        "            (page.locator(sel).press('Enter') if sel else page.keyboard.press('Enter'))\n"
        "    print(json.dumps({'ok': True, 'url': page.url, 'title': page.title()}))\n"
        "PY"
    )


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
            "or decision point as soon as it is ready. "
            "Do not tell the user to press Allow — the consent card in the thread is that UI."
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
        name="send_file",
        description=(
            "Attach a file to this chat so the owner can download it. "
            "Use a path under this computer's home (or workspace), or pass content "
            "plus a name for a generated file. Do not only mention the path."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "File under this bot's home or workspace, e.g. notes.txt or Downloads/report.pdf",
                },
                "name": {
                    "type": "string",
                    "description": "Download filename if different from the path.",
                },
                "content": {
                    "type": "string",
                    "description": "Optional text to write first, then attach (max 1 MB).",
                },
                "text": {
                    "type": "string",
                    "description": "Optional caption shown above the file card.",
                },
            },
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
        description=(
            "Save one short durable sentence about the owner or this chat. "
            "Call this when the user states a preference, rule, person, project, place, "
            "or correction. Default scope is shared (every bot sees it). "
            "Use scope=bot only for a note that belongs to this chat. "
            "Do not store one-off tasks such as opening a tab. "
            "A new note on the same slot (name, city, tz, tone, format, language) replaces the old one. "
            "To erase something, set forget=true with the text to drop."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "content": {
                    "type": "string",
                    "description": "One short sentence to remember, or the text to forget.",
                },
                "kind": {
                    "type": "string",
                    "description": (
                        "preference, choice, rule, person, project, place, "
                        "desktop, correction, or workflow."
                    ),
                },
                "scope": {
                    "type": "string",
                    "description": "user (shared, default) or bot (this chat only).",
                },
                "slot": {
                    "type": "string",
                    "description": "Optional singleton topic: name, city, tz, tone, format, language.",
                },
                "forget": {
                    "type": "boolean",
                    "description": "If true, delete matching saved notes instead of adding one.",
                },
                "path": {
                    "type": "string",
                    "description": "Optional document path. Leave empty to append a unique entry.",
                },
            },
            "required": ["content"],
        },
    ),
    ToolSpec(
        name="read_owner_file",
        description=(
            "Read a file from the owner's paired computer through the desktop client. "
            "Does not ask permission. Without a paired window this fails."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Absolute or ~ path on the owner's computer.",
                }
            },
            "required": ["path"],
        },
    ),
    ToolSpec(
        name="write_owner_file",
        description=(
            "Create or overwrite a file on the owner's paired computer. "
            "Asks Allow once / Always / Deny once for writes on that PC. Path stays under the owner's home."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Absolute or ~ path on the owner's computer.",
                },
                "content": {
                    "type": "string",
                    "description": "File text to write.",
                },
            },
            "required": ["path", "content"],
        },
    ),
    ToolSpec(
        name="list_owner_dir",
        description=(
            "List a directory on the owner's paired computer. "
            "Does not ask permission. Without a paired window this fails. "
            "On a Russian desktop ~/Downloads is often ~/Загрузки. This Pi's files are under cwd."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Absolute or ~ directory on the owner's computer. Default is the home.",
                }
            },
        },
    ),
    ToolSpec(
        name="run_owner_command",
        description=(
            "Run a shell command on the owner's paired computer, like an SSH session. "
            "Read-only commands (ls, cat, echo, pwd, uname, …) run without a card. "
            "Commands that can change the PC ask Allow once / Always / Deny once for that bot. "
            "cwd stays under the owner's home. Without a paired window this fails."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "Shell command to run as the owner.",
                },
                "cwd": {
                    "type": "string",
                    "description": "Working directory. Default is the owner's home.",
                },
            },
            "required": ["command"],
        },
    ),
    ToolSpec(
        name="open_path",
        description=(
            "Open a URL or workspace file on this bot's Pi desktop. "
            "Opening a website asks the owner Allow once / Always / Deny first."
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
            "(e.g. 'chromium', 'files', 'terminal'), optionally with a URI/URL. "
            "'files' opens the home folder in the file manager."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "application": {
                    "type": "string",
                    "description": "Application name or binary to launch (chromium, files, terminal).",
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
        description=(
            "Look at this bot's Linux desktop: geometry, cursor, and the active window title. "
            "Default is slim (no screenshot). Set include_image only when the title cannot answer "
            "(captcha, canvas, unlabeled buttons). Prefer DOM / curl after the owner allowed the site."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "include_image": {
                    "type": "boolean",
                    "description": "Attach a typed screenshot only when pixels are required.",
                },
            },
            "additionalProperties": False,
        },
    ),
    ToolSpec(
        name="computer_act",
        description=(
            "Send mouse, keyboard, or launch actions to this bot's Linux desktop. "
            "Opening a site, clicking, typing, or filling a form asks Allow once / Always / Deny first. "
            "Pass several actions in one call. Set return_observe to get a slim observe after the last action."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "actions": {
                    "type": "array",
                    "description": "Ordered desktop actions (click, move, type, key, scroll, wait, open, launch, close).",
                    "items": {"type": "object"},
                },
                "return_observe": {
                    "type": "boolean",
                    "description": "After the actions, return a slim observe (title/geometry, image only if the title is generic).",
                },
            },
            "required": ["actions"],
        },
    ),
    ToolSpec(
        name="browser_act",
        description=(
            "Drive the remote Chromium: open a URL, fill a field, click, type, or submit. "
            "Use this for forms and page actions. The owner must Allow once / Always / Deny first. "
            "Do not use Playwright or CDP to skip this card."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "origin": {
                    "type": "string",
                    "description": "Site origin if already known, e.g. https://example.com",
                },
                "actions": {
                    "type": "array",
                    "description": (
                        "Ordered page actions: goto (url), fill (selector, text), "
                        "click (selector), type (text), press (key), submit (selector?)."
                    ),
                    "items": {"type": "object"},
                },
            },
            "required": ["actions"],
        },
    ),
    ToolSpec(
        name="request_takeover",
        description=(
            "Pause this turn and ask the human to take control of this bot's desktop "
            "(login, captcha, or any page you cannot complete). Pass a short reason. "
            "Do not invent a password. Do not keep calling tools after this."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "reason": {
                    "type": "string",
                    "description": "What the owner should do in the browser, then Release.",
                },
            },
            "additionalProperties": False,
        },
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

    def _exec_remember(self, args: dict[str, Any], bound_bot_id: str | None) -> dict[str, Any]:
        content = str(args.get("content") or "").strip()
        path = str(args.get("path") or "").strip()
        if not content:
            return {"ok": False, "error": "content cannot be empty"}
        bot_id, run_id, thread_id = self.runtime.resolve_turn_context(bound_bot_id)
        forget = bool(args.get("forget"))
        kind = str(args.get("kind") or "preference")
        if args.get("scope"):
            scope = str(args.get("scope"))
        elif getattr(self.runtime, "resolve_turn_role", lambda: "lead")() == "subagent":
            scope = "bot"
        else:
            scope = "user"
        hub = getattr(self.runtime, "memory", None)
        if hub is not None:
            try:
                if forget:
                    removed = hub.forget(content, bot_id=bot_id)
                    return {"ok": True, "forgotten": removed}
                entry = hub.capture(
                    content,
                    kind=kind,
                    scope=scope,
                    bot_id=bot_id,
                    source="remember",
                    run_id=run_id,
                    thread_id=thread_id,
                    slot=str(args.get("slot") or "") or None,
                )
                if entry is None:
                    return {"ok": True, "saved": False}
                return {
                    "ok": True,
                    "entry_id": entry.id,
                    "document_id": entry.document_id,
                    "scope": entry.scope,
                    "kind": entry.kind,
                }
            except Exception as exc:
                log.exception("failed to save memory in remember tool")
                return {"ok": False, "error": str(exc)}
        if self.runtime.store is not None:
            try:
                if not path or path == "MEMORY.md":
                    from artek_buddy.db.shaping import new_id
                    from artek_buddy.memory_hub import entry_path, normalize_kind

                    path = entry_path(
                        new_id("ment"),
                        normalize_kind(kind),
                        "charter" if scope == "bot" else "owner",
                    )
                doc = self.runtime.store.save_memory(
                    scope="bot" if scope == "bot" and bot_id else "user",
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

    def _exec_read_owner_file(self, args: dict[str, Any], bound_bot_id: str | None) -> dict[str, Any]:
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
                name, data = str(raw[0]), raw[1] if isinstance(raw[1], bytes) else str(raw[1]).encode()
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
                data = found["_data"] if isinstance(found["_data"], bytes) else str(found["_data"]).encode()
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

    def _exec_write_owner_file(self, args: dict[str, Any], bound_bot_id: str | None) -> dict[str, Any]:
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
        return _with_consent({"ok": True, "path": str(found.get("path") or path), "bytes": found.get("bytes", len(text.encode()))})

    def _exec_list_owner_dir(self, args: dict[str, Any], bound_bot_id: str | None) -> dict[str, Any]:
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
        return _with_consent({"ok": True, "path": str(found.get("path") or path), "entries": found.get("entries") or []})

    def _exec_run_owner_command(self, args: dict[str, Any], bound_bot_id: str | None) -> dict[str, Any]:
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
        return _with_consent({
            "ok": True,
            "stdout": str(found.get("stdout") or ""),
            "stderr": str(found.get("stderr") or ""),
            "exit_code": int(found.get("exit_code") or 0),
        })

    def _exec_computer_observe(self, args: dict[str, Any], bound_bot_id: str | None) -> dict[str, Any]:
        found = self._require_computer(bound_bot_id)
        if isinstance(found, dict):
            return found
        bot, _bot_id = found
        try:
            return self.runtime.computers.observe(bot, include_image=bool(args.get("include_image")))
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
        needs_page = False
        for item in actions:
            if not isinstance(item, dict):
                continue
            kind = str(item.get("kind") or "")
            target = str(item.get("url") or item.get("path") or item.get("uri") or "")
            origin = browse_origin(target)
            if origin:
                denied = self._deny(
                    _bot_id,
                    CLASS_BROWSE,
                    origin,
                    f"Open {origin} on the remote desktop?",
                )
                if denied:
                    return denied
            if kind in PAGE_KINDS:
                needs_page = True
        if needs_page:
            denied = self._deny_page(_bot_id, self._page_origin(actions))
            if denied:
                return denied
        try:
            return self.runtime.computers.act(
                bot,
                actions,
                return_observe=bool(args.get("return_observe")),
            )
        except Exception as exc:
            log.exception("computer_act failed")
            return {"ok": False, "error": str(exc)}

    def _exec_browser_act(self, args: dict[str, Any], bound_bot_id: str | None) -> dict[str, Any]:
        found = self._require_computer(bound_bot_id)
        if isinstance(found, dict):
            return found
        bot, _bot_id = found
        actions = args.get("actions")
        if not isinstance(actions, list) or not actions:
            return {"ok": False, "error": "actions must be a non-empty list"}
        origin = self._page_origin(actions, str(args.get("origin") or ""))
        needs_page = False
        for item in actions:
            if not isinstance(item, dict):
                continue
            kind = str(item.get("kind") or "")
            target = str(item.get("url") or item.get("path") or item.get("uri") or "")
            site = browse_origin(target)
            if site:
                denied = self._deny(
                    _bot_id,
                    CLASS_BROWSE,
                    site,
                    f"Open {site} on the remote desktop?",
                )
                if denied:
                    return denied
            if kind in {"fill", "type", "click", "press", "submit", "key"}:
                needs_page = True
        if needs_page:
            denied = self._deny_page(_bot_id, origin)
            if denied:
                return denied
        runner = getattr(self.runtime.computers, "browser_act", None)
        if callable(runner):
            try:
                return runner(bot, actions)
            except Exception as exc:
                log.exception("browser_act failed")
                return {"ok": False, "error": str(exc)}
        exec_fn = getattr(self.runtime.computers, "exec_command", None)
        if callable(exec_fn):
            try:
                return exec_fn(bot, _playwright_browser_command(actions))
            except Exception as exc:
                log.exception("browser_act exec failed")
                return {"ok": False, "error": str(exc)}
        mapped: list[dict[str, Any]] = []
        for item in actions:
            if not isinstance(item, dict):
                continue
            kind = str(item.get("kind") or "")
            if kind == "goto":
                url = str(item.get("url") or item.get("path") or "")
                if url:
                    mapped.append({"kind": "open", "path": url})
            elif kind in {"fill", "type"}:
                mapped.append({"kind": "type", "text": str(item.get("text") or "")})
            elif kind == "press":
                mapped.append({"kind": "key", "key": str(item.get("key") or "Return")})
            elif kind in {"click", "submit"}:
                mapped.append({"kind": "key", "key": "Return"} if kind == "submit" else item)
        try:
            return self.runtime.computers.act(bot, mapped or actions)
        except Exception as exc:
            log.exception("browser_act fallback failed")
            return {"ok": False, "error": str(exc)}

    def _exec_open_path(self, args: dict[str, Any], bound_bot_id: str | None) -> dict[str, Any]:
        found = self._require_computer(bound_bot_id)
        if isinstance(found, dict):
            return found
        bot, _bot_id = found
        path = str(args.get("path") or args.get("url") or "").strip()
        if not path:
            return {"ok": False, "error": "path is required"}
        origin = browse_origin(path)
        if origin:
            denied = self._deny(
                _bot_id,
                CLASS_BROWSE,
                origin,
                f"Open {origin} on the remote desktop?",
            )
            if denied:
                return denied
        try:
            res = self.runtime.computers.open_path(bot, path)
            if self.runtime.events is not None:
                emit_computer_event(self.runtime.events, bot, self.runtime.computers.status(bot))
            if isinstance(res, dict) and origin and getattr(self.runtime, "consent", None) is not None:
                return _with_consent(res)
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
        origin = browse_origin(uri or "")
        if origin:
            denied = self._deny(
                _bot_id,
                CLASS_BROWSE,
                origin,
                f"Open {origin} on the remote desktop?",
            )
            if denied:
                return denied
        try:
            res = self.runtime.computers.launch_app(bot, app_name, uri=uri)
            if self.runtime.events is not None:
                emit_computer_event(self.runtime.events, bot, self.runtime.computers.status(bot))
            if isinstance(res, dict) and origin and getattr(self.runtime, "consent", None) is not None:
                return _with_consent(res)
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
        reason = str(args.get("reason") or args.get("text") or "").strip() or (
            "Take control of this computer, then Release when you are done."
        )
        try:
            self.runtime.store.mark_run_waiting_takeover(run_id)
        except Exception as exc:
            log.exception("failed to mark waiting_takeover")
            return {"ok": False, "error": str(exc)}
        if self.runtime.on_takeover_requested:
            try:
                self.runtime.on_takeover_requested(bot_id, run_id, reason)
            except TypeError:
                self.runtime.on_takeover_requested(bot_id, run_id)
            except Exception:
                log.exception("takeover callback failed")
        return {"ok": True, "waiting": True, "reason": reason}

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

    def _agent_file_roots(self, bot_id: str | None) -> list[Path]:
        roots: list[Path] = []
        home = Path(self.runtime.home_cwd(bot_id))
        roots.append(home)
        workspace = Path(getattr(self.runtime.settings, "agent_cwd", "") or home)
        if workspace.resolve() != home.resolve():
            roots.append(workspace)
        return roots

    def _resolve_agent_file(self, bot_id: str | None, raw: str) -> Path | None:
        text = str(raw or "").strip()
        if not text:
            return None
        path = Path(text)
        roots = self._agent_file_roots(bot_id)
        candidates: list[Path] = []
        if path.is_absolute():
            candidates.append(path)
        else:
            candidates.extend(root / path for root in roots)
        for candidate in candidates:
            try:
                resolved = candidate.resolve()
            except OSError:
                continue
            if resolved.is_file() and any(_is_under(resolved, root) for root in roots):
                return resolved
        return None

    def _exec_send_file(self, args: dict[str, Any], bound_bot_id: str | None) -> dict[str, Any]:
        bot_id, run_id, _thread_id = self.runtime.resolve_turn_context(bound_bot_id)
        path_raw = str(args.get("path") or "").strip()
        display = _safe_filename(str(args.get("name") or path_raw or "file"))
        caption = str(args.get("text") or "").strip()
        content = args.get("content")
        source: Path | None = None
        if content is not None:
            if not isinstance(content, str):
                return {"ok": False, "error": "content must be text"}
            data = content.encode("utf-8")
            if len(data) > MAX_INLINE_FILE_BYTES:
                return {"ok": False, "error": "content is too large"}
            if not path_raw:
                path_raw = display
            home = Path(self.runtime.home_cwd(bot_id))
            home.mkdir(parents=True, exist_ok=True)
            source = home / _safe_filename(path_raw)
            source.write_bytes(data)
        else:
            source = self._resolve_agent_file(bot_id, path_raw)
        if source is None or not source.is_file():
            return {"ok": False, "error": "file not found"}
        size = source.stat().st_size
        if size > MAX_SEND_FILE_BYTES:
            return {"ok": False, "error": "file too large"}
        name = _safe_filename(str(args.get("name") or source.name or display))
        mime = mimetypes.guess_type(name)[0] or "application/octet-stream"
        store = getattr(self.runtime, "store", None)
        if store is None or not hasattr(store, "save_artifact"):
            return {"ok": False, "error": "artifacts unavailable"}
        bot = store.get_bot(bot_id) if bot_id else None
        if bot is None:
            return {"ok": False, "error": "bot not found"}
        artifact_id = new_id("art")
        dest_dir = Path(self.runtime.settings.agent_data_dir) / "artifacts" / bot.id
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / artifact_id
        shutil.copy2(source, dest)
        try:
            store.save_artifact(
                bot_id=bot.id,
                name=name,
                mime_type=mime,
                size=size,
                storage_path=str(dest),
                run_id=run_id,
                artifact_id=artifact_id,
            )
        except Exception as exc:
            dest.unlink(missing_ok=True)
            return {"ok": False, "error": str(exc)}
        blocks: list[dict[str, Any]] = []
        if caption:
            blocks.append({"kind": "text", "text": caption})
        blocks.append(
            {
                "kind": "file",
                "artifact_id": artifact_id,
                "name": name,
                "mime_type": mime,
                "size": size,
            }
        )
        posted = self._append_bot_blocks(args, bound_bot_id, blocks)
        if not posted.get("ok"):
            return posted
        posted["artifact_id"] = artifact_id
        posted["name"] = name
        posted["size"] = size
        return posted

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
