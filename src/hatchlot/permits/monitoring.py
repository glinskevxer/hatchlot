"""Discharge monitoring, and the two ways a permit is failed.

Nearly every permit carries two numbers for the same parameter: a daily maximum
that no single sample may exceed, and a monthly average that the month's samples
together may not exceed. A station can pass every daily maximum and fail the
month, and the other way around, so both are worked out here and reported
separately.

The monthly average is over the samples that were taken, which means missing a
sampling day is not a neutral act. A month with two samples in it and a bad one
reads much worse than a month with twenty, and the count is reported with the
average so nobody has to guess.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from ..calendar import DateRange, parse_date
from ..errors import ValidationError
from ..journal import JournalLog
from ..numeric import Number, require_positive, safe_divide
from .limits import Limit, Parameter, Sample


@dataclass(frozen=True, slots=True)
class Reading:
    """One dated sample at one outfall."""

    day: date
    outfall: str
    sample: Sample
    taken_by: str

    def __post_init__(self) -> None:
        from ..identifiers import normalise_code

        object.__setattr__(self, "day", parse_date(self.day))
        object.__setattr__(self, "outfall", normalise_code(self.outfall, field="outfall"))
        if not self.taken_by.strip():
            raise ValidationError("a reading needs whoever took it", field="taken_by")
        object.__setattr__(self, "taken_by", self.taken_by.strip())

    @property
    def parameter(self) -> Parameter:
        return self.sample.parameter


@dataclass(frozen=True, slots=True)
class Exceedance:
    """One sample over one limit, with everything a report needs on it."""

    day: date
    outfall: str
    limit: Limit
    value: Decimal

    @property
    def over_by(self) -> Decimal:
        return self.value - self.limit.value

    @property
    def share(self) -> Decimal:
        return safe_divide(self.value, self.limit.value, field="limit")


class MonitoringRecord(JournalLog[Reading]):
    """Every reading the station has taken."""

    def __init__(self) -> None:
        super().__init__(lambda entry: entry.day, lambda entry: entry.outfall)

    def for_outfall(self, outfall: str) -> tuple[Reading, ...]:
        return self._for_key(outfall)

    def for_parameter(
        self, parameter: Parameter, window: DateRange | None = None
    ) -> tuple[Reading, ...]:
        entries = self.within(window) if window is not None else self.all()
        return tuple(entry for entry in entries if entry.parameter is parameter)

    def daily_exceedances(
        self, limit: Limit, window: DateRange | None = None
    ) -> tuple[Exceedance, ...]:
        """Every single sample over a limit."""

        found: list[Exceedance] = []
        for reading in self.for_parameter(limit.parameter, window):
            value = reading.sample.value_for(limit)
            if value > limit.value:
                found.append(
                    Exceedance(
                        day=reading.day,
                        outfall=reading.outfall,
                        limit=limit,
                        value=value,
                    )
                )
        return tuple(found)

    def average_for(self, limit: Limit, window: DateRange) -> Decimal:
        """The mean of a window's samples against a limit."""

        readings = self.for_parameter(limit.parameter, window)
        if not readings:
            raise ValidationError("no samples in that window", field="window")
        total = sum((reading.sample.value_for(limit) for reading in readings), Decimal(0))
        return total / Decimal(len(readings))

    def sample_count(self, parameter: Parameter, window: DateRange) -> int:
        return len(self.for_parameter(parameter, window))

    def average_exceeds(self, limit: Limit, window: DateRange) -> bool:
        return self.average_for(limit, window) > limit.value

    def is_frequency_met(
        self, parameter: Parameter, window: DateRange, *, per_month: int = 4
    ) -> bool:
        """Whether the permit's sampling frequency was actually kept.

        Counted per thirty days of the window rather than per calendar month, so
        a quarterly report answers on the same arithmetic as a monthly one.
        """

        if per_month < 1:
            raise ValidationError("a frequency is at least one", field="per_month")
        # Rounded to nearest rather than up, so a thirty one day month does not
        # quietly demand a fifth sample against a four a month permit.
        required = (Decimal(window.days) / Decimal(30) * Decimal(per_month)).to_integral_value(
            rounding="ROUND_HALF_UP"
        )
        return Decimal(self.sample_count(parameter, window)) >= required

    def outfalls(self) -> tuple[str, ...]:
        return self.keys()


def worst_exceedance(exceedances: tuple[Exceedance, ...]) -> Exceedance | None:
    """The one furthest over its limit, as a share rather than a difference."""

    if not exceedances:
        return None
    return max(exceedances, key=lambda entry: entry.share)


def exceedance_days(exceedances: tuple[Exceedance, ...]) -> int:
    """How many separate days had an exceedance on them."""

    return len({entry.day for entry in exceedances})


def compliance_share(record: MonitoringRecord, limit: Limit, window: DateRange) -> Decimal:
    """The share of a window's samples that were inside a limit."""

    readings = record.for_parameter(limit.parameter, window)
    if not readings:
        raise ValidationError("no samples in that window", field="window")
    inside = len(
        [reading for reading in readings if reading.sample.value_for(limit) <= limit.value]
    )
    return safe_divide(inside, len(readings), field="window")


def next_due(record: MonitoringRecord, outfall: str, *, interval_days: Number = 7) -> date | None:
    """When the next sample at an outfall falls due."""

    from datetime import timedelta

    days = require_positive(interval_days, field="interval_days")
    readings = record.for_outfall(outfall)
    if not readings:
        return None
    return readings[-1].day + timedelta(days=int(days))
