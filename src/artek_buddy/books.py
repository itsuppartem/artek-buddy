from __future__ import annotations

import re

from artek_buddy.contracts.domain import SkillBook

MAX_BOOKS = 20
MAX_NAME = 64
MAX_WHEN = 280
MAX_BODY = 16_384
_SLUG_PIECE = re.compile(r"[^a-z0-9]+")


class BookError(ValueError):
    def __init__(self, detail: str) -> None:
        super().__init__(detail)
        self.detail = detail


def book_slug(name: str) -> str:
    slug = _SLUG_PIECE.sub("-", (name or "").strip().lower()).strip("-")
    return slug[:MAX_NAME]


def normalize_book(name: str, when_to_use: str, body: str) -> tuple[str, str, str, str]:
    title = " ".join((name or "").split())
    when = " ".join((when_to_use or "").split())
    steps = (body or "").strip()
    if not title:
        raise BookError("name cannot be empty")
    if len(title) > MAX_NAME:
        raise BookError(f"name is longer than {MAX_NAME} characters")
    slug = book_slug(title)
    if not slug:
        raise BookError("name needs a letter or number")
    if not when:
        raise BookError("when_to_use cannot be empty")
    if len(when) > MAX_WHEN:
        raise BookError(f"when_to_use is longer than {MAX_WHEN} characters")
    if not steps:
        raise BookError("body cannot be empty")
    if len(steps) > MAX_BODY:
        raise BookError(f"body is longer than {MAX_BODY} characters")
    return title, when, steps, slug


def format_book_catalog(books: list[SkillBook]) -> str | None:
    if not books:
        return None
    lines = [
        "<skill_books>",
        "Playbooks for this chat. The next turn sees names only.",
        "Open a book with open_book before following its steps.",
        "Teach a new one with save_book. Drop one with forget_book.",
    ]
    for book in books:
        lines.append(f"- {book.name} — {book.when_to_use}")
    lines.append("</skill_books>")
    return "\n".join(lines)
