from __future__ import annotations

import unittest
from datetime import datetime, timezone

from artek_buddy.cron import CronError, next_run_at, parse_cron, validate_timezone


class CronTest(unittest.TestCase):
    def test_parse_five_fields(self) -> None:
        minutes, hours, days, months, weekdays = parse_cron("*/5 9-17 * * 1-5")
        self.assertIn(0, minutes)
        self.assertIn(5, minutes)
        self.assertNotIn(1, minutes)
        self.assertEqual(hours, set(range(9, 18)))
        self.assertEqual(weekdays, {1, 2, 3, 4, 5})

    def test_sunday_seven_maps_to_zero(self) -> None:
        _minutes, _hours, _days, _months, weekdays = parse_cron("0 0 * * 7")
        self.assertEqual(weekdays, {0})

    def test_invalid_cron(self) -> None:
        with self.assertRaises(CronError):
            parse_cron("0 9 * *")
        with self.assertRaises(CronError):
            parse_cron("60 * * * *")
        with self.assertRaises(CronError):
            parse_cron("")

    def test_next_every_five_minutes(self) -> None:
        after = datetime(2026, 8, 17, 10, 1, tzinfo=timezone.utc)
        nxt = next_run_at("*/5 * * * *", after)
        self.assertEqual(nxt, datetime(2026, 8, 17, 10, 5, tzinfo=timezone.utc))

    def test_next_daily_hour(self) -> None:
        before = datetime(2026, 8, 17, 8, 0, tzinfo=timezone.utc)
        self.assertEqual(next_run_at("0 9 * * *", before), datetime(2026, 8, 17, 9, 0, tzinfo=timezone.utc))
        at = datetime(2026, 8, 17, 9, 0, tzinfo=timezone.utc)
        self.assertEqual(next_run_at("0 9 * * *", at), datetime(2026, 8, 18, 9, 0, tzinfo=timezone.utc))

    def test_timezone(self) -> None:
        self.assertEqual(validate_timezone("UTC"), "UTC")
        with self.assertRaises(CronError):
            validate_timezone("Not/AZone")


if __name__ == "__main__":
    unittest.main()
