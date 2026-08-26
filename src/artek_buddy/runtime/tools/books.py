from __future__ import annotations

from typing import Any

from artek_buddy.books import BookError


class BooksToolsMixin:
    def _book_card(
        self,
        args: dict[str, Any],
        bound_bot_id: str | None,
        name: str,
        action: str,
        text: str,
    ) -> None:
        self._append_bot_blocks(
            args,
            bound_bot_id,
            [{"kind": "book", "name": name, "action": action, "text": text}],
            mark_sent=False,
        )

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
        self._book_card(
            args,
            bound_bot_id,
            book.name,
            "saved",
            f"Saved. Say please run {book.name} later.",
        )
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
        self._book_card(args, bound_bot_id, book.name, "opened", book.body[:800])
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
        self._book_card(args, bound_bot_id, book.name, "forgotten", "Forgotten.")
        return {"ok": True, "name": book.name}
