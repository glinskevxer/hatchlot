"""Dates, the way a hatchery counts them.

Two things here are not the standard library's answer. A hatchery year does not
start in January, it starts when the first eggs are taken, so a brood year runs
from a configured month. And a date range in this package is closed at both
ends, because a form that says 1 March to 31 March means both those days.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from .errors import ValidationError

_FORMATS = ("%Y-%m-%d", "%m/%d/%Y", "%d %b %Y", "%Y%m%d")


def parse_date(value: object, *, field: str = "date") -> date:
    """Read a date out of anything a form or a datalogger hands over."""

    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if not isinstance(value, str):
        raise ValidationError(f"{type(value).__name__} is not a date", field=field)
    text = value.strip()
    if not text:
        raise ValidationError("empty date", field=field)
    for fmt in _FORMATS:
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    raise ValidationError(f"{value!r} is not a date this package reads", field=field)


def parse_timestamp(value: object, *, field: str = "timestamp") -> datetime:
    """Read a datalogger timestamp, tolerating a date with no time on it."""

    if isinstance(value, datetime):
        return value
    if isinstance(value, date):
        return datetime(value.year, value.month, value.day)
    if not isinstance(value, str):
        raise ValidationError(f"{type(value).__name__} is not a timestamp", field=field)
    text = value.strip().replace("T", " ")
    if not text:
        raise ValidationError("empty timestamp", field=field)
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%m/%d/%Y %H:%M"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return datetime.combine(parse_date(text, field=field), datetime.min.time())


@dataclass(frozen=True, slots=True, order=True)
class DateRange:
    """A closed interval of days. Both ends are inside it."""

    start: date
    end: date

    def __init__(self, start: object, end: object) -> None:
        first = parse_date(start, field="start")
        last = parse_date(end, field="end")
        if last < first:
            raise ValidationError(f"{last} is before {first}", field="end")
        object.__setattr__(self, "start", first)
        object.__setattr__(self, "end", last)

    @property
    def days(self) -> int:
        """How many days the range covers, counting both ends."""

        return (self.end - self.start).days + 1

    def __contains__(self, day: object) -> bool:
        return self.start <= parse_date(day) <= self.end

    def __iter__(self) -> Iterator[date]:
        day = self.start
        while day <= self.end:
            yield day
            day += timedelta(days=1)

    def overlaps(self, other: DateRange) -> bool:
        return self.start <= other.end and other.start <= self.end

    def intersection(self, other: DateRange) -> DateRange | None:
        if not self.overlaps(other):
            return None
        return DateRange(max(self.start, other.start), min(self.end, other.end))

    def clipped_to(self, other: DateRange) -> DateRange:
        """This range cut down to `other`, refusing a pair that never meet."""

        result = self.intersection(other)
        if result is None:
            raise ValidationError(f"{self} does not overlap {other}", field="range")
        return result

    def extended(self, days: int) -> DateRange:
        """The same range with its end pushed out by whole days."""

        return DateRange(self.start, self.end + timedelta(days=days))

    def __str__(self) -> str:
        return f"{self.start.isoformat()}..{self.end.isoformat()}"

    @classmethod
    def parse(cls, text: str) -> DateRange:
        parts = text.split("..")
        if len(parts) != 2:
            raise ValidationError(f"{text!r} is not a date range", field="range")
        return cls(parts[0].strip(), parts[1].strip())

    @classmethod
    def month_of(cls, day: object) -> DateRange:
        """The whole calendar month a day falls in."""

        anchor = parse_date(day)
        start = anchor.replace(day=1)
        if start.month == 12:
            end = start.replace(year=start.year + 1, month=1) - timedelta(days=1)
        else:
            end = start.replace(month=start.month + 1) - timedelta(days=1)
        return cls(start, end)


def brood_year_of(day: object, *, start_month: int = 7) -> int:
    """Which brood year a date belongs to.

    A station takes its first eggs in the late summer, so the production year is
    named for the calendar year the take started in and runs on into the next.
    """

    if not 1 <= start_month <= 12:
        raise ValidationError(f"{start_month} is not a month", field="start_month")
    anchor = parse_date(day)
    return anchor.year if anchor.month >= start_month else anchor.year - 1


def brood_year_range(year: int, *, start_month: int = 7) -> DateRange:
    """The window of days that belong to a brood year."""

    if not 1 <= start_month <= 12:
        raise ValidationError(f"{start_month} is not a month", field="start_month")
    start = date(year, start_month, 1)
    end = date(year + 1, start_month, 1) - timedelta(days=1)
    return DateRange(start, end)


def add_months(day: object, months: int) -> date:
    """Move a date by whole months, landing on the last day of a short month."""

    anchor = parse_date(day)
    total = anchor.month - 1 + months
    year = anchor.year + total // 12
    month = total % 12 + 1
    last = _days_in_month(year, month)
    return date(year, month, min(anchor.day, last))


def _days_in_month(year: int, month: int) -> int:
    following = date(year + 1, 1, 1) if month == 12 else date(year, month + 1, 1)
    return (following - date(year, month, 1)).days


def days_between(first: object, second: object) -> int:
    """Signed whole days from `first` to `second`."""

    return (parse_date(second, field="second") - parse_date(first, field="first")).days
