from __future__ import annotations

from artek_buddy.books import MAX_BOOKS, BookError, book_slug, normalize_book
from artek_buddy.contracts.domain import SkillBook
from artek_buddy.db.shaping import isoformat_utc, new_id, parse_iso


class BooksMixin:
    def list_skill_books(self, bot_id: str) -> list[SkillBook]:
        with self._conn() as conn:
            rows = conn.execute(
                """
                SELECT id, bot_id, name, slug, when_to_use, updated_at
                FROM skill_books
                WHERE bot_id = %s
                ORDER BY name ASC
                """,
                (bot_id,),
            ).fetchall()
            conn.commit()
        return [self._book_view(row) for row in rows]

    def get_skill_book(self, bot_id: str, name: str) -> SkillBook | None:
        slug = book_slug(name)
        if not slug:
            return None
        with self._conn() as conn:
            row = conn.execute(
                """
                SELECT id, bot_id, name, slug, when_to_use, body, updated_at
                FROM skill_books
                WHERE bot_id = %s AND slug = %s
                """,
                (bot_id, slug),
            ).fetchone()
            conn.commit()
        return self._book_view(row, body=True) if row else None

    def save_skill_book(self, bot_id: str, name: str, when_to_use: str, body: str) -> SkillBook:
        title, when, steps, slug = normalize_book(name, when_to_use, body)
        now = isoformat_utc()
        book_id = new_id("bok")
        with self._conn() as conn:
            existing = conn.execute(
                "SELECT id FROM skill_books WHERE bot_id = %s AND slug = %s",
                (bot_id, slug),
            ).fetchone()
            if existing is None:
                count = conn.execute(
                    "SELECT COUNT(*) AS n FROM skill_books WHERE bot_id = %s",
                    (bot_id,),
                ).fetchone()
                if int((count or {}).get("n") or 0) >= MAX_BOOKS:
                    raise BookError(f"this chat already has {MAX_BOOKS} books")
                conn.execute(
                    """
                    INSERT INTO skill_books (
                        id, bot_id, name, slug, when_to_use, body, created_at, updated_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (book_id, bot_id, title, slug, when, steps, now, now),
                )
            else:
                book_id = str(existing["id"])
                conn.execute(
                    """
                    UPDATE skill_books
                    SET name = %s, when_to_use = %s, body = %s, updated_at = %s
                    WHERE id = %s
                    """,
                    (title, when, steps, now, book_id),
                )
            conn.commit()
        found = self.get_skill_book(bot_id, title)
        if found is None:
            raise BookError("could not save that book")
        return found

    def forget_skill_book(self, bot_id: str, name: str) -> SkillBook | None:
        found = self.get_skill_book(bot_id, name)
        if found is None:
            return None
        with self._conn() as conn:
            conn.execute(
                "DELETE FROM skill_books WHERE bot_id = %s AND slug = %s",
                (bot_id, found.slug),
            )
            conn.commit()
        return found

    def _book_view(self, row: dict, *, body: bool = False) -> SkillBook:
        return SkillBook(
            id=str(row["id"]),
            bot_id=str(row["bot_id"]),
            name=str(row["name"]),
            slug=str(row["slug"]),
            when_to_use=str(row["when_to_use"]),
            body=str(row["body"]) if body and row.get("body") is not None else None,
            updated_at=parse_iso(row["updated_at"]),
        )
