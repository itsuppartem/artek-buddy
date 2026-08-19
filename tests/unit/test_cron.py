from __future__ import annotations

from datetime import datetime, timezone

import pytest

from artek_buddy.cron import CronError, next_run_at, parse_cron, validate_timezone


def test_parse_cron_happy() -> None:
    minutes, hours, days, months, weekdays = parse_cron("0 9 * * 1")
    assert minutes == {0}
    assert hours == {9}
    assert 1 in weekdays


def test_parse_cron_rejects_bad_shape() -> None:
    with pytest.raises(CronError):
        parse_cron("0 9 *")
    with pytest.raises(CronError):
        parse_cron("99 9 * * *")
    with pytest.raises(CronError):
        parse_cron("")


def test_timezone_and_next_run() -> None:
    assert validate_timezone("UTC") == "UTC"
    with pytest.raises(CronError):
        validate_timezone("Not/AZone")
    after = datetime(2026, 8, 19, 8, 0, tzinfo=timezone.utc)
    nxt = next_run_at("0 9 * * *", after=after, timezone_name="UTC")
    assert nxt.hour == 9
    assert nxt.minute == 0
