from __future__ import annotations

import json
from collections.abc import Iterator
from typing import Any


def tool_name(tool_call: Any) -> str:
    if not isinstance(tool_call, dict):
        return "tool"
    nested = tool_call.get("function")
    if isinstance(nested, dict) and nested.get("name"):
        return str(nested["name"])
    for key in ("name", "toolName", "tool_name"):
        value = tool_call.get(key)
        if value:
            return str(value)
    return "tool"


def tool_args(tool_call: Any) -> dict[str, Any]:
    if not isinstance(tool_call, dict):
        return {}
    args = tool_call.get("arguments") or tool_call.get("args") or tool_call.get("input") or {}
    if isinstance(args, str):
        try:
            parsed = json.loads(args)
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            return {"raw": args}
    if isinstance(args, dict):
        return args
    nested = tool_call.get("function")
    if isinstance(nested, dict):
        return tool_args(nested)
    return {}


def assistant_text(message: Any) -> str:
    content = getattr(getattr(message, "message", None), "content", None) or ()
    parts: list[str] = []
    for block in content:
        text = getattr(block, "text", None)
        if text:
            parts.append(str(text))
    return "".join(parts)


def _map_tool_to_events(
    call_id: str,
    tname: str,
    args: dict[str, Any],
    status: str,
) -> list[tuple[str, dict[str, Any]]]:
    # Raw Cursor tools (mcp, read, shell, …) stay off the thread.
    # The chat shows answers, thinking, worker cards, and a few product facts.
    if tname == "remember":
        # Remembered / Forgot come from the tool only when a row actually changed.
        return []
    if tname == "run_subagent":
        sname = str(args.get("name") or "subagent")
        task = str(args.get("task") or "")
        return [
            (
                "thread.subagent",
                {
                    "agent_id": call_id,
                    "name": sname,
                    "task": task,
                    "status": "running" if status == "running" else "completed",
                },
            )
        ]
    if tname == "spawn_bot" and status == "completed":
        return [
            (
                "bot.spawned",
                {
                    "bot_id": call_id,
                    "name": str(args.get("name") or "bot"),
                    "title": str(args.get("title") or ""),
                    "status": "created",
                },
            )
        ]
    return []


def map_cursor_event(event: Any) -> list[tuple[str, dict[str, Any]]]:
    """Map one Cursor run event to product event type + payload. No IDs yet."""
    kind = getattr(event, "kind", "")
    out: list[tuple[str, dict[str, Any]]] = []
    if kind == "interaction_update":
        upd = getattr(event, "interaction_update", None)
        typ = getattr(upd, "type", None)
        if typ == "text-delta":
            text = getattr(upd, "text", "") or ""
            if text:
                out.append(("thread.message.updated", {"delta": text, "kind": "text"}))
        elif typ == "thinking-delta":
            pass
        elif typ == "tool-call-started":
            tool = getattr(upd, "tool_call", None) or {}
            call_id = getattr(upd, "call_id", "") or ""
            tname = tool_name(tool)
            args = tool_args(tool)
            out.extend(_map_tool_to_events(call_id, tname, args, "running"))
        elif typ == "tool-call-completed":
            tool = getattr(upd, "tool_call", None) or {}
            call_id = getattr(upd, "call_id", "") or ""
            tname = tool_name(tool)
            args = tool_args(tool)
            out.extend(_map_tool_to_events(call_id, tname, args, "completed"))
        return out

    if kind == "sdk_message":
        msg = getattr(event, "sdk_message", None)
        mtype = getattr(msg, "type", "")
        if mtype == "tool_call":
            call_id = getattr(msg, "call_id", "") or ""
            tname = getattr(msg, "name", None) or "tool"
            args = getattr(msg, "args", None) or {}
            if not isinstance(args, dict):
                args = {}
            status = getattr(msg, "status", None) or "running"
            out.extend(_map_tool_to_events(call_id, tname, args, status))
        elif mtype == "thinking":
            pass
        elif mtype == "assistant":
            text = assistant_text(msg)
            if text:
                out.append(
                    ("thread.message.updated", {"text": text, "kind": "text", "replace": True})
                )
        return out

    if kind == "result":
        result = getattr(event, "result", None) or {}
        if isinstance(result, dict):
            text = result.get("result") or result.get("text")
            if isinstance(text, str) and text:
                out.append(
                    ("thread.message.updated", {"text": text, "kind": "text", "replace": True})
                )
    return out


def accumulate(draft: str, payload: dict[str, Any]) -> str:
    incoming = payload.get("text")
    if incoming and (payload.get("replace") or not payload.get("delta")):
        text = str(incoming)
        if not draft:
            return text
        if text.startswith(draft) or draft.startswith(text):
            return text if len(text) >= len(draft) else draft
        if payload.get("replace"):
            return text
        return draft
    delta = payload.get("delta") or ""
    return draft + str(delta)


def snapshot_payload(draft: str, kind: str = "text") -> dict[str, Any]:
    return {"text": draft, "kind": kind}


def iter_mapped(event: Any) -> Iterator[tuple[str, dict[str, Any]]]:
    yield from map_cursor_event(event)
