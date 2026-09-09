from __future__ import annotations

from typing import Any


def _activity_fields(item: Any) -> dict[str, Any]:
    empty = not (getattr(item, "progress", None) or "").strip()
    return {
        "progress": item.progress,
        "progress_remaining": getattr(item, "progress_remaining", None),
        "progress_empty": empty,
        "text_update": "no text update" if empty else "has text",
        "last_activity_at": item.last_activity_at,
        "activity_seq": item.activity_seq,
        "last_activity_kind": item.last_activity_kind,
        "last_tool_name": item.last_tool_name,
        "tool_running": item.tool_running,
    }


def _inspected_seq(args: dict[str, Any]) -> int | None:
    raw = args.get("inspected_activity_seq")
    if raw is None or raw == "":
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


class SubagentToolsMixin:
    def _require_subagents(self, bound_bot_id: str | None) -> tuple[Any, Any] | dict[str, Any]:
        bot_id, run_id, _thread_id = self.runtime.resolve_turn_context(bound_bot_id)
        if self.runtime.subagents is None or self.runtime.store is None or not bot_id:
            return {"ok": False, "error": "subagents are not available"}
        bot = self.runtime.store.get_bot(bot_id)
        if bot is None:
            return {"ok": False, "error": "bot not found"}
        return bot, run_id

    def _exec_spawn_subagent(
        self, args: dict[str, Any], bound_bot_id: str | None
    ) -> dict[str, Any]:
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

    def _exec_list_subagents(
        self, args: dict[str, Any], bound_bot_id: str | None
    ) -> dict[str, Any]:
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
                    "clarifications": item.clarifications,
                    **_activity_fields(item),
                }
                for item in rows
            ],
        }

    def _exec_inspect_subagent(
        self, args: dict[str, Any], bound_bot_id: str | None
    ) -> dict[str, Any]:
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
            "result": item.result,
            "error": item.error,
            "clarifications": item.clarifications,
            **_activity_fields(item),
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
            item = self.runtime.subagents.stop(
                bot,
                ref,
                owner=False,
                inspected_activity_seq=_inspected_seq(args),
            )
        except Exception as exc:
            return {"ok": False, "error": str(exc)}
        return {"ok": True, "id": item.id, "index": item.index, "status": item.status}

    def _exec_restart_subagent(
        self, args: dict[str, Any], bound_bot_id: str | None
    ) -> dict[str, Any]:
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

    def _exec_steer_subagent(
        self, args: dict[str, Any], bound_bot_id: str | None
    ) -> dict[str, Any]:
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

    def _exec_report_progress(
        self, args: dict[str, Any], bound_bot_id: str | None
    ) -> dict[str, Any]:
        found = self._require_subagents(bound_bot_id)
        if isinstance(found, dict):
            return found
        bot, run_id = found
        if not run_id:
            return {"ok": False, "error": "worker run is required"}
        try:
            return self.runtime.subagents.report_progress(
                bot,
                run_id,
                str(args.get("step") or ""),
                args.get("remaining"),
            )
        except Exception as exc:
            return {"ok": False, "error": str(exc)}
