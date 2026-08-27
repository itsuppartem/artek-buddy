from __future__ import annotations

from datetime import UTC, datetime

from artek_buddy.db.shaping import (
    TURN_FAILED,
    isoformat_utc,
    owner_visible_error,
    strip_markdown,
)


def test_isoformat_utc_orders_runs_in_the_same_second() -> None:
    first = datetime(2026, 8, 21, 9, 0, 5, 1, tzinfo=UTC)
    second = datetime(2026, 8, 21, 9, 0, 5, 2, tzinfo=UTC)
    assert isoformat_utc(first) < isoformat_utc(second)
    assert isoformat_utc(first) != isoformat_utc(first.replace(microsecond=0))


def test_strip_markdown_removes_nested_html_leftovers() -> None:
    assert strip_markdown("<<b>hi") == "hi"


def test_strip_markdown_bounds_a_long_unclosed_markdown_prefix() -> None:
    blob = "![" * 4000 + "x"
    assert strip_markdown(blob)
    assert "<" not in strip_markdown("<" * 4000 + "hi")


def test_owner_visible_error_drops_raw_run_id() -> None:
    raw = "run failed: run-fb7fd73f-32ed-43ed-a22f-a561aab1600a"
    assert owner_visible_error(raw) == TURN_FAILED
    assert owner_visible_error(None, "run_abc") == TURN_FAILED
    assert owner_visible_error("run failed: run_abc", "run_abc") == TURN_FAILED
    assert owner_visible_error("scripted fail") == "scripted fail"
