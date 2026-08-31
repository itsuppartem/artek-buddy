from __future__ import annotations

import re

from artek_buddy.contracts.domain import SkillBook

MAX_BOOKS = 20
MAX_NAME = 64
MAX_WHEN = 280
MAX_BODY = 16_384
_SLUG_PIECE = re.compile(r"[^a-z0-9]+")
_FRONTMATTER = re.compile(r"\A---\s*\n(.*?)\n---\s*\n?", re.DOTALL)


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


def parse_skill_document(raw: str) -> tuple[str, str, str]:
    text = (raw or "").replace("\r\n", "\n")
    stripped = text.strip()
    if not stripped:
        raise BookError("body cannot be empty")
    name = ""
    when = ""
    match = _FRONTMATTER.match(stripped)
    if match:
        for line in match.group(1).splitlines():
            if ":" not in line:
                continue
            key, value = line.split(":", 1)
            key = key.strip().lower()
            value = value.strip().strip("\"'")
            if key == "name":
                name = value
            elif key in {"description", "when_to_use"}:
                when = value
    if not name:
        heading = re.search(r"^#\s+(.+)$", stripped, re.MULTILINE)
        name = heading.group(1).strip() if heading else ""
    if not when and name:
        when = f"When the owner asks for {name}"
    title, trigger, body, _slug = normalize_book(name, when, stripped)
    return title, trigger, body


def format_book_catalog(books: list[SkillBook]) -> str | None:
    if not books:
        return None
    lines = [
        "<skill_books>",
        "Skills kept for this chat. The next turn sees names only.",
        "Open a matching book yourself with open_book before following its steps. "
        "Do not wait for the owner to name or trigger it.",
        "Find and keep a published skill with install_book. Drop one with forget_book.",
    ]
    for book in books:
        lines.append(f"- {book.name} — {book.when_to_use}")
    lines.append("</skill_books>")
    return "\n".join(lines)
