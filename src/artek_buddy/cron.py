from __future__ import annotations

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

FIELD_RANGES = (
    (0, 59),
    (0, 23),
    (1, 31),
    (1, 12),
    (0, 7),
)


class CronError(ValueError):
    pass


def validate_timezone(name: str) -> str:
    value = (name or "UTC").strip() or "UTC"
    try:
        ZoneInfo(value)
    except (ZoneInfoNotFoundError, KeyError) as err:
        raise CronError(f"unknown timezone: {value}") from err
    return value


def parse_cron(expr: str) -> tuple[set[int], set[int], set[int], set[int], set[int]]:
    parts = (expr or "").strip().split()
    if len(parts) != 5:
        raise CronError("cron must have 5 fields")
    parsed = []
    for index, part in enumerate(parts):
        low, high = FIELD_RANGES[index]
        parsed.append(_parse_field(part, low, high, weekday=index == 4))
    return parsed[0], parsed[1], parsed[2], parsed[3], parsed[4]


def next_run_at(expr: str, after: datetime | None = None, timezone_name: str = "UTC") -> datetime:
    minutes, hours, days, months, weekdays = parse_cron(expr)
    tz = ZoneInfo(validate_timezone(timezone_name))
    moment = after or datetime.now(timezone.utc)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    local = moment.astimezone(tz).replace(second=0, microsecond=0) + timedelta(minutes=1)
    for _ in range(366 * 24 * 60 + 2):
        if _matches(local, minutes, hours, days, months, weekdays):
            return local.astimezone(timezone.utc)
        local += timedelta(minutes=1)
    raise CronError("no next run within a year")


def _parse_field(raw: str, low: int, high: int, weekday: bool = False) -> set[int]:
    values: set[int] = set()
    for chunk in raw.split(","):
        piece = chunk.strip()
        if not piece:
            raise CronError("empty cron field")
        step = 1
        if "/" in piece:
            piece, step_raw = piece.split("/", 1)
            try:
                step = int(step_raw)
            except ValueError as err:
                raise CronError(f"invalid cron step: {chunk}") from err
            if step < 1:
                raise CronError(f"invalid cron step: {chunk}")
        if piece in {"*", "?"}:
            start, end = low, high
        elif "-" in piece:
            start_raw, end_raw = piece.split("-", 1)
            start, end = _int(start_raw), _int(end_raw)
        else:
            start = end = _int(piece)
        if start > end or start < low or end > high:
            raise CronError(f"cron field out of range: {chunk}")
        values.update(range(start, end + 1, step))
    if weekday and 7 in values:
        values.add(0)
        values.discard(7)
    return values


def _int(raw: str) -> int:
    try:
        return int(raw)
    except ValueError as err:
        raise CronError(f"invalid cron number: {raw}") from err


def _matches(
    local: datetime,
    minutes: set[int],
    hours: set[int],
    days: set[int],
    months: set[int],
    weekdays: set[int],
) -> bool:
    if local.minute not in minutes or local.hour not in hours or local.month not in months:
        return False
    dom_star = days == set(range(1, 32))
    dow_star = weekdays == set(range(0, 7))
    cron_dow = (local.weekday() + 1) % 7
    if dom_star and dow_star:
        return True
    if not dom_star and not dow_star:
        return local.day in days or cron_dow in weekdays
    if not dom_star:
        return local.day in days
    return cron_dow in weekdays
