from __future__ import annotations

from datetime import UTC, datetime

from artek_buddy.db.shaping import isoformat_utc


def test_isoformat_utc_orders_runs_in_the_same_second() -> None:
    first = datetime(2026, 8, 21, 9, 0, 5, 1, tzinfo=UTC)
    second = datetime(2026, 8, 21, 9, 0, 5, 2, tzinfo=UTC)
    assert isoformat_utc(first) < isoformat_utc(second)
    assert isoformat_utc(first) != isoformat_utc(first.replace(microsecond=0))
