from __future__ import annotations

from datetime import datetime, timezone

from artek_buddy.db.shaping import isoformat_utc


def test_isoformat_utc_orders_runs_in_the_same_second() -> None:
    first = datetime(2026, 8, 21, 9, 0, 5, 1, tzinfo=timezone.utc)
    second = datetime(2026, 8, 21, 9, 0, 5, 2, tzinfo=timezone.utc)
    assert isoformat_utc(first) < isoformat_utc(second)
    assert isoformat_utc(first) != isoformat_utc(first.replace(microsecond=0))
