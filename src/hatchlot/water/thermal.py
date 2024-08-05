"""Thermal units, and what to do about the days the probe did not record.

Incubation does not run on days, it runs on degrees. A chinook egg needs about
850 Celsius degree days above zero before it hatches, and whether that takes
sixty days or a hundred is the water's business. So the series of daily
temperatures is the clock, and a hole in the series is a hole in the clock.

Three policies cover a hole, and the choice is the caller's, because a missing
day in a hatchery record is sometimes a broken probe and sometimes a day nobody
worked. Guessing which one it was is not this module's job.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from enum import Enum

from ..calendar import DateRange, parse_date
from ..errors import ValidationError
from ..numeric import Number, to_decimal
from ..quantities.temperature import Temperature


class GapPolicy(Enum):
    """What a missing day does to an accumulation."""

    REFUSE = "refuse"
    CARRY_FORWARD = "carry_forward"
    INTERPOLATE = "interpolate"


@dataclass(frozen=True, slots=True, order=True)
class DailyTemperature:
    """One day's mean water temperature."""

    day: date
    celsius: Decimal

    def __init__(self, day: object, temperature: Temperature | Decimal | str | float) -> None:
        object.__setattr__(self, "day", parse_date(day))
        if isinstance(temperature, Temperature):
            celsius = temperature.celsius
        else:
            celsius = Temperature(to_decimal(temperature, field="temperature"), "C").celsius
        object.__setattr__(self, "celsius", celsius)

    @property
    def temperature(self) -> Temperature:
        return Temperature(self.celsius, "C")


class ThermalSeries:
    """A station's daily temperatures for one water, indexed by day."""

    def __init__(self, readings: Iterable[DailyTemperature] = ()) -> None:
        self._days: dict[date, Decimal] = {}
        for reading in readings:
            self.record(reading)

    def record(self, reading: DailyTemperature) -> None:
        """Add or replace a day. The last value written for a day wins."""

        self._days[reading.day] = reading.celsius

    def add(self, day: object, celsius: Temperature | Decimal | str | float) -> None:
        self.record(DailyTemperature(day, celsius))

    def __len__(self) -> int:
        return len(self._days)

    def __contains__(self, day: object) -> bool:
        return parse_date(day) in self._days

    def __iter__(self) -> Iterator[DailyTemperature]:
        for day in sorted(self._days):
            yield DailyTemperature(day, self._days[day])

    @property
    def covered(self) -> DateRange | None:
        """The first and last day recorded, which is not the same as complete."""

        if not self._days:
            return None
        return DateRange(min(self._days), max(self._days))

    def get(self, day: object) -> Decimal | None:
        return self._days.get(parse_date(day))

    def missing_days(self, window: DateRange) -> tuple[date, ...]:
        return tuple(day for day in window if day not in self._days)

    def _value_for(self, day: date, policy: GapPolicy) -> Decimal:
        known = self._days.get(day)
        if known is not None:
            return known
        if policy is GapPolicy.REFUSE:
            raise ValidationError(f"no temperature recorded for {day}", field="series")
        earlier = [d for d in self._days if d < day]
        later = [d for d in self._days if d > day]
        if not earlier:
            raise ValidationError(f"nothing recorded before {day} to fill it in", field="series")
        previous = max(earlier)
        if policy is GapPolicy.CARRY_FORWARD or not later:
            return self._days[previous]
        following = min(later)
        span = Decimal((following - previous).days)
        step = (self._days[following] - self._days[previous]) / span
        return self._days[previous] + step * Decimal((day - previous).days)

    def mean(self, window: DateRange, policy: GapPolicy = GapPolicy.REFUSE) -> Temperature:
        """The mean temperature over a window."""

        values = [self._value_for(day, policy) for day in window]
        return Temperature(sum(values, Decimal(0)) / Decimal(len(values)), "C")

    def accumulate(
        self,
        window: DateRange,
        *,
        zero_point_c: Number = 0,
        policy: GapPolicy = GapPolicy.REFUSE,
    ) -> Decimal:
        """Thermal units over a window, above a species zero point.

        A day colder than the zero point contributes nothing rather than a
        negative, because development does not run backwards.
        """

        zero = to_decimal(zero_point_c, field="zero_point_c")
        total = Decimal(0)
        for day in window:
            above = self._value_for(day, policy) - zero
            if above > 0:
                total += above
        return total

    def day_units_reach(
        self,
        start: object,
        target_units: Number,
        *,
        zero_point_c: Number = 0,
        policy: GapPolicy = GapPolicy.REFUSE,
        limit_days: int = 800,
    ) -> date | None:
        """The first day an accumulation from `start` reaches `target_units`.

        `None` means the series ran out before the target did, which is the
        normal answer partway through an incubation.
        """

        target = to_decimal(target_units, field="target_units")
        if target <= 0:
            raise ValidationError("a target of zero units is not a question", field="target_units")
        if not self._days:
            return None
        zero = to_decimal(zero_point_c, field="zero_point_c")
        day = parse_date(start)
        total = Decimal(0)
        for _ in range(limit_days):
            if policy is GapPolicy.REFUSE and day not in self._days:
                return None
            if day not in self._days and day > max(self._days, default=day):
                return None
            above = self._value_for(day, policy) - zero
            if above > 0:
                total += above
            if total >= target:
                return day
            day += timedelta(days=1)
        return None

    def projected_day(
        self,
        start: object,
        target_units: Number,
        mean_celsius: Number,
        *,
        zero_point_c: Number = 0,
    ) -> date:
        """Where the target lands if the water holds at a stated mean.

        Used when the series has not been written yet, which is most of the time
        a hatchery manager is asked when a lot will be ready.
        """

        target = to_decimal(target_units, field="target_units")
        rate = to_decimal(mean_celsius, field="mean_celsius") - to_decimal(zero_point_c)
        if rate <= 0:
            raise ValidationError("water at or below the zero point never gets there", field="mean")
        days = int((target / rate).to_integral_value(rounding="ROUND_CEILING"))
        return parse_date(start) + timedelta(days=max(days - 1, 0))
