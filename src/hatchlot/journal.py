"""A dated log, since three modules had each grown their own.

Monitoring readings, picks, treatments and feedings are all the same structure:
entries that arrive out of order, are kept in date order, and get sliced by a
key and by a window. The three copies had drifted. One sorted on
insert, one sorted on read, and one only sorted when it remembered to.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Iterator
from datetime import date, datetime
from typing import Generic, TypeVar

from .calendar import DateRange, parse_date
from .errors import ValidationError
from .identifiers import normalise_code

T = TypeVar("T")


class Journal(Generic[T]):
    """Entries in date order, sliceable by subject and by window."""

    def __init__(
        self,
        day_of: Callable[[T], date | datetime],
        key_of: Callable[[T], str],
    ) -> None:
        self.day_of = day_of
        self.key_of = key_of
        self._items: list[T] = []

    def record(self, entry: T) -> T:
        self._items.append(entry)
        self._items.sort(key=self._sort_key)
        return entry

    def extend(self, entries: Iterable[T]) -> None:
        for entry in entries:
            self.record(entry)

    def _sort_key(self, entry: T) -> tuple[date, str]:
        return (_as_date(self.day_of(entry)), self.key_of(entry))

    def __len__(self) -> int:
        return len(self._items)

    def __iter__(self) -> Iterator[T]:
        return iter(list(self._items))

    def all(self) -> tuple[T, ...]:
        return tuple(self._items)

    def keys(self) -> tuple[str, ...]:
        return tuple(sorted({self.key_of(entry) for entry in self._items}))

    def for_key(self, key: str) -> tuple[T, ...]:
        code = normalise_code(key, field="key")
        return tuple(entry for entry in self._items if self.key_of(entry) == code)

    def within(self, window: DateRange) -> tuple[T, ...]:
        return tuple(entry for entry in self._items if _as_date(self.day_of(entry)) in window)

    def on_day(self, day: object) -> tuple[T, ...]:
        when = parse_date(day)
        return tuple(entry for entry in self._items if _as_date(self.day_of(entry)) == when)

    def latest(self, key: str) -> T | None:
        entries = self.for_key(key)
        return entries[-1] if entries else None

    def first(self, key: str) -> T | None:
        entries = self.for_key(key)
        return entries[0] if entries else None

    def span(self) -> DateRange:
        """The days the journal covers, refusing an empty one."""

        if not self._items:
            raise ValidationError("an empty journal covers nothing", field="journal")
        days = [_as_date(self.day_of(entry)) for entry in self._items]
        return DateRange(min(days), max(days))


def _as_date(value: date | datetime) -> date:
    return value.date() if isinstance(value, datetime) else value
