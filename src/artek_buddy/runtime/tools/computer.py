from __future__ import annotations

from typing import Any

from artek_buddy.consent import (
    CLASS_BROWSE,
    browse_origin,
)
from artek_buddy.runtime.tools.common import (
    PAGE_KINDS,
    _playwright_browser_command,
    _with_consent,
    emit_computer_event,
    log,
)


class ComputerToolsMixin:
    def _require_computer(self, bound_bot_id: str | None) -> tuple[Any, Any] | dict[str, Any]:
        bot_id, _run_id, _thread_id = self.runtime.resolve_turn_context(bound_bot_id)
        if self.runtime.computers is None or self.runtime.store is None or not bot_id:
            return {"ok": False, "error": "computer is not available"}
        bot = self.runtime.store.get_bot(bot_id)
        if bot is None:
            return {"ok": False, "error": "bot not found"}
        return bot, bot_id

    def _publish_computer(self, bot: Any) -> None:
        if self.runtime.events is None or self.runtime.computers is None:
            return
        emit_computer_event(self.runtime.events, bot, self.runtime.computers.status(bot))

    def _exec_computer_observe(
        self, args: dict[str, Any], bound_bot_id: str | None
    ) -> dict[str, Any]:
        found = self._require_computer(bound_bot_id)
        if isinstance(found, dict):
            return found
        bot, _bot_id = found
        try:
            result = self.runtime.computers.observe(
                bot, include_image=bool(args.get("include_image"))
            )
            self._publish_computer(bot)
            return result
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
            result = self.runtime.computers.act(
                bot,
                actions,
                return_observe=bool(args.get("return_observe")),
            )
            self._publish_computer(bot)
            return result
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
                result = runner(bot, actions)
                self._publish_computer(bot)
                return result
            except Exception as exc:
                log.exception("browser_act failed")
                return {"ok": False, "error": str(exc)}
        exec_fn = getattr(self.runtime.computers, "exec_command", None)
        if callable(exec_fn):
            try:
                result = exec_fn(bot, _playwright_browser_command(actions))
                self._publish_computer(bot)
                return result
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
            result = self.runtime.computers.act(bot, mapped or actions)
            self._publish_computer(bot)
            return result
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
            self._publish_computer(bot)
            if (
                isinstance(res, dict)
                and origin
                and getattr(self.runtime, "consent", None) is not None
            ):
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
            self._publish_computer(bot)
            if (
                isinstance(res, dict)
                and origin
                and getattr(self.runtime, "consent", None) is not None
            ):
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
            self._publish_computer(bot)
            return res
        except Exception as exc:
            log.exception("close_app failed")
            return {"ok": False, "error": str(exc)}

    def _exec_request_takeover(
        self, args: dict[str, Any], bound_bot_id: str | None
    ) -> dict[str, Any]:
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
