"""Mortality, and telling background loss from an event.

Fish die every day and the number means nothing until it is a rate against the
population carrying it. What a station acts on is a change in that rate, and
what a station reports is the cause split, because a month of predation and a
month of gas bubble disease call for different money.

The daily rate here is expressed per thousand fish, which is how every hatchery
form this package has to agree with writes it.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from enum import Enum

from ..calendar import DateRange, parse_date
from ..errors import ValidationError
from ..identifiers import normalise_code
from ..journal import JournalLog
from ..numeric import Number, require_positive, safe_divide


class MortalityCause(Enum):
    """Why the fish died, in the categories a production report uses."""

    DISEASE = "disease"
    PREDATION = "predation"
    HANDLING = "handling"
    GAS = "gas"
    OXYGEN = "oxygen"
    TEMPERATURE = "temperature"
    UNKNOWN = "unknown"

    @property
    def is_preventable(self) -> bool:
        """The ones a station is expected to have controlled."""

        return self in {
            MortalityCause.HANDLING,
            MortalityCause.GAS,
            MortalityCause.OXYGEN,
            MortalityCause.TEMPERATURE,
        }


@dataclass(frozen=True, slots=True, order=True)
class MortalityRecord:
    """One day's dead fish off one lot."""

    day: date
    lot: str
    count: Decimal
    cause: MortalityCause
    recorded_by: str

    def __init__(
        self,
        day: object,
        lot: str,
        count: Number,
        cause: MortalityCause,
        recorded_by: str,
    ) -> None:
        object.__setattr__(self, "day", parse_date(day))
        object.__setattr__(self, "lot", normalise_code(lot, field="lot"))
        object.__setattr__(self, "count", require_positive(count, field="count"))
        if not isinstance(cause, MortalityCause):
            raise ValidationError(f"{cause!r} is not a mortality cause", field="cause")
        object.__setattr__(self, "cause", cause)
        if not recorded_by.strip():
            raise ValidationError("a mortality record needs whoever made it", field="recorded_by")
        object.__setattr__(self, "recorded_by", recorded_by.strip())


class MortalityLog(JournalLog[MortalityRecord]):
    """Every mortality record on the station."""

    def __init__(self, records: Iterable[MortalityRecord] = ()) -> None:
        super().__init__(lambda record: record.day, lambda record: record.lot, records)

    def for_lot(self, lot: str) -> tuple[MortalityRecord, ...]:
        return self._for_key(lot)

    def total(self, lot: str, window: DateRange | None = None) -> Decimal:
        records = self.for_lot(lot)
        if window is not None:
            records = tuple(record for record in records if record.day in window)
        return sum((record.count for record in records), Decimal(0))

    def by_cause(self, lot: str, window: DateRange | None = None) -> dict[MortalityCause, Decimal]:
        totals: dict[MortalityCause, Decimal] = {}
        records = self.for_lot(lot)
        if window is not None:
            records = tuple(record for record in records if record.day in window)
        for record in records:
            totals[record.cause] = totals.get(record.cause, Decimal(0)) + record.count
        return totals

    def preventable_share(self, lot: str) -> Decimal:
        """The share of a lot's mortality the station is answerable for."""

        totals = self.by_cause(lot)
        overall = sum(totals.values(), Decimal(0))
        if overall == 0:
            return Decimal(0)
        preventable = sum(
            (count for cause, count in totals.items() if cause.is_preventable), Decimal(0)
        )
        return preventable / overall

    def daily_rate(self, lot: str, day: object, population: Number) -> Decimal:
        """Deaths per thousand fish on one day."""

        held = require_positive(population, field="population")
        when = parse_date(day)
        dead = sum((record.count for record in self.for_lot(lot) if record.day == when), Decimal(0))
        return safe_divide(dead, held, field="population") * Decimal(1000)

    def rolling_rate(self, lot: str, day: object, population: Number, days: int = 7) -> Decimal:
        """Mean deaths per thousand per day over a window ending on a day."""

        if days < 1:
            raise ValidationError("a rolling window needs a day in it", field="days")
        held = require_positive(population, field="population")
        when = parse_date(day)
        window = DateRange(when - timedelta(days=days - 1), when)
        dead = sum(
            (record.count for record in self.for_lot(lot) if record.day in window), Decimal(0)
        )
        return safe_divide(dead, held, field="population") * Decimal(1000) / Decimal(days)

    def is_event(self, lot: str, day: object, population: Number, *, threshold: Number = 5) -> bool:
        """Whether a day's rate is over the station's line for an event."""

        return self.daily_rate(lot, day, population) > require_positive(
            threshold, field="threshold"
        )

    def worst_day(self, lot: str) -> MortalityRecord | None:
        records = self.for_lot(lot)
        return max(records, key=lambda record: record.count) if records else None


def cumulative_survival(ponded: Number, dead: Number) -> Decimal:
    """The share of a ponded population still alive after a mortality total."""

    start = require_positive(ponded, field="ponded")
    lost = require_positive(dead, field="dead") if dead else Decimal(0)
    if lost > start:
        raise ValidationError("more fish died than were ponded", field="dead")
    return (start - lost) / start
