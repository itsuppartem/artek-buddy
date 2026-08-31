from __future__ import annotations

import pytest

from artek_buddy.book_fetch import blocked_fetch_url
from artek_buddy.books import (
    MAX_BODY,
    MAX_NAME,
    BookError,
    book_slug,
    format_book_catalog,
    normalize_book,
    parse_skill_document,
)
from artek_buddy.contracts.domain import SkillBook
from artek_buddy.memory import wrap_turn_prompt


def test_book_slug_and_normalize() -> None:
    assert book_slug("Invoice PDF") == "invoice-pdf"
    title, when, body, slug = normalize_book(
        "  Invoice  ",
        "When I say invoice",
        "Open the site.\nDownload the PDF.",
    )
    assert title == "Invoice"
    assert slug == "invoice"
    assert when == "When I say invoice"
    assert "Download" in body
    with pytest.raises(BookError, match="name cannot be empty"):
        normalize_book("   ", "when", "body")
    with pytest.raises(BookError, match="letter or number"):
        normalize_book("!!!", "when", "body")
    with pytest.raises(BookError, match="when_to_use cannot be empty"):
        normalize_book("Invoice", "  ", "body")
    with pytest.raises(BookError, match="body cannot be empty"):
        normalize_book("Invoice", "when", "  ")
    with pytest.raises(BookError, match="name is longer"):
        normalize_book("x" * (MAX_NAME + 1), "when", "body")
    with pytest.raises(BookError, match="body is longer"):
        normalize_book("Invoice", "when", "x" * (MAX_BODY + 1))


def test_catalog_stays_names_only_and_rides_in_the_turn() -> None:
    assert format_book_catalog([]) is None
    text = format_book_catalog(
        [
            SkillBook(
                id="bok_1",
                bot_id="bot_1",
                name="Invoice",
                slug="invoice",
                when_to_use="When I say invoice",
                body="SECRET STEPS",
                updated_at="2026-08-26T00:00:00Z",
            )
        ]
    )
    assert text is not None
    assert "Invoice" in text
    assert "When I say invoice" in text
    assert "SECRET STEPS" not in text
    assert "open_book" in text
    assert "install_book" in text
    assert "teach" not in text.lower()
    wrapped = wrap_turn_prompt("hello", None, role="lead", books_context=text)
    assert "<skill_books>" in wrapped
    assert "install_book" in wrapped
    assert "teaches a procedure" not in wrapped
    assert "SECRET STEPS" not in wrapped


def test_parse_skill_document_keeps_fetched_markdown() -> None:
    raw = (
        "---\n"
        "name: Invoice\n"
        "description: When I say invoice\n"
        "---\n"
        "\n"
        "Open the invoice site and download the PDF.\n"
    )
    name, when, body = parse_skill_document(raw)
    assert name == "Invoice"
    assert when == "When I say invoice"
    assert "Open the invoice site and download the PDF." in body
    assert "when I say invoice" in body.lower() or "Open the invoice site" in body


def test_host_must_not_fetch_loopback_private_or_link_local() -> None:
    assert blocked_fetch_url("http://127.0.0.1/SKILL.md") is not None
    assert blocked_fetch_url("http://localhost/SKILL.md") is not None
    assert blocked_fetch_url("http://10.0.0.1/SKILL.md") is not None
    assert blocked_fetch_url("http://192.168.1.8/SKILL.md") is not None
    assert blocked_fetch_url("http://169.254.169.254/latest/meta-data/") is not None
    assert blocked_fetch_url("http://[::1]/SKILL.md") is not None
    assert blocked_fetch_url("file:///etc/passwd") is not None
    assert blocked_fetch_url("ftp://example.com/SKILL.md") is not None
    assert blocked_fetch_url("https://example.com/skills/invoice/SKILL.md") is None
