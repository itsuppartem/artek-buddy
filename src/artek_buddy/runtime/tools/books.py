from __future__ import annotations

from typing import Any

from artek_buddy.book_fetch import fetch_skill_document
from artek_buddy.books import BookError, parse_skill_document
from artek_buddy.consent import CLASS_BROWSE, browse_origin
from artek_buddy.runtime.tools.common import _with_consent


class BooksToolsMixin:
    def _exec_install_book(self, args: dict[str, Any], bound_bot_id: str | None) -> dict[str, Any]:
        store = getattr(self.runtime, "store", None)
        bot_id, _run_id, _thread_id = self.runtime.resolve_turn_context(bound_bot_id)
        if store is None or not bot_id:
            return {"ok": False, "error": "store is not available"}
        url = str(args.get("url") or "").strip()
        origin = browse_origin(url)
        if not origin:
            return {"ok": False, "error": "url must be http or https"}
        denied = self._deny(
            bot_id,
            CLASS_BROWSE,
            origin,
            f"Install a skill from {origin}?",
        )
        if denied:
            return denied
        allow_url = str(getattr(self.runtime, "book_fixture_url", "") or "").strip() or None
        try:
            raw = fetch_skill_document(url, allow_url=allow_url)
            name, when, body = parse_skill_document(raw)
            book = store.save_skill_book(bot_id, name, when, body)
        except BookError as err:
            return {"ok": False, "error": err.detail}
        return _with_consent({"ok": True, "id": book.id, "name": book.name, "slug": book.slug})

    def _exec_save_book(self, args: dict[str, Any], bound_bot_id: str | None) -> dict[str, Any]:
        store = getattr(self.runtime, "store", None)
        bot_id, _run_id, _thread_id = self.runtime.resolve_turn_context(bound_bot_id)
        if store is None or not bot_id:
            return {"ok": False, "error": "store is not available"}
        try:
            book = store.save_skill_book(
                bot_id,
                str(args.get("name") or ""),
                str(args.get("when_to_use") or ""),
                str(args.get("body") or ""),
            )
        except BookError as err:
            return {"ok": False, "error": err.detail}
        return {"ok": True, "id": book.id, "name": book.name, "slug": book.slug}

    def _exec_open_book(self, args: dict[str, Any], bound_bot_id: str | None) -> dict[str, Any]:
        store = getattr(self.runtime, "store", None)
        bot_id, _run_id, _thread_id = self.runtime.resolve_turn_context(bound_bot_id)
        if store is None or not bot_id:
            return {"ok": False, "error": "store is not available"}
        name = str(args.get("name") or "")
        book = store.get_skill_book(bot_id, name)
        if book is None or not book.body:
            return {"ok": False, "error": "book not found"}
        return {"ok": True, "name": book.name, "body": book.body}

    def _exec_forget_book(self, args: dict[str, Any], bound_bot_id: str | None) -> dict[str, Any]:
        store = getattr(self.runtime, "store", None)
        bot_id, _run_id, _thread_id = self.runtime.resolve_turn_context(bound_bot_id)
        if store is None or not bot_id:
            return {"ok": False, "error": "store is not available"}
        name = str(args.get("name") or "")
        book = store.forget_skill_book(bot_id, name)
        if book is None:
            return {"ok": False, "error": "book not found"}
        return {"ok": True, "name": book.name}
