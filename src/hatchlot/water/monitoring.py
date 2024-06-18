"""The reading log, and the excursions that fall out of it.

A crew walks the units twice a day with a meter, and once a year somebody has to
answer a question about a single afternoon eighteen months ago. So readings go
in a log, and the log knows how to collapse a run of bad readings into one
excursion with a start, an end and a worst value, because that is the form the
question is always asked in.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum

from ..calendar import DateRange, parse_timestamp
from ..errors import ValidationError
from ..identifiers import normalise_code
from ..numeric import Number, require_non_negative, to_decimal
from ..quantities.temperature import Temperature


class ExcursionKind(Enum):
    """What was wrong with the water."""

    LOW_OXYGEN = "low_oxygen"
    HIGH_TEMPERATURE = "high_temperature"
    LOW_TEMPERATURE = "low_temperature"


@dataclass(frozen=True, slots=True)
class Thresholds:
    """The lines a station draws on its own units."""

    minimum_oxygen_mgL: Decimal = Decimal("6.0")
    maximum_celsius: Decimal = Decimal("16.0")
    minimum_celsius: Decimal = Decimal("2.0")

    def __post_init__(self) -> None:
        if self.minimum_celsius >= self.maximum_celsius:
            raise ValidationError("the temperature band is inverted", field="minimum_celsius")
        require_non_negative(self.minimum_oxygen_mgL, field="minimum_oxygen_mgL")


@dataclass(frozen=True, slots=True, order=True)
class Reading:
    """One meter reading on one unit."""

    taken_at: datetime
    container: str
    celsius: Decimal
    oxygen_mgL: Decimal

    def __init__(
        self, taken_at: object, container: str, temperature: Temperature, oxygen_mgL: Number
    ) -> None:
        object.__setattr__(self, "taken_at", parse_timestamp(taken_at))
        object.__setattr__(self, "container", normalise_code(container, field="container"))
        object.__setattr__(self, "celsius", temperature.celsius)
        object.__setattr__(self, "oxygen_mgL", require_non_negative(oxygen_mgL, field="oxygen"))

    @property
    def temperature(self) -> Temperature:
        return Temperature(self.celsius, "C")

    def breaches(self, thresholds: Thresholds) -> tuple[ExcursionKind, ...]:
        """Every line this one reading crosses, which can be more than one."""

        found: list[ExcursionKind] = []
        if self.oxygen_mgL < thresholds.minimum_oxygen_mgL:
            found.append(ExcursionKind.LOW_OXYGEN)
        if self.celsius > thresholds.maximum_celsius:
            found.append(ExcursionKind.HIGH_TEMPERATURE)
        if self.celsius < thresholds.minimum_celsius:
            found.append(ExcursionKind.LOW_TEMPERATURE)
        return tuple(found)


@dataclass(frozen=True, slots=True)
class Excursion:
    """A run of consecutive readings on one unit that were all wrong the same way."""

    container: str
    kind: ExcursionKind
    started_at: datetime
    ended_at: datetime
    worst: Decimal
    readings: int

    @property
    def duration_hours(self) -> Decimal:
        seconds = Decimal((self.ended_at - self.started_at).total_seconds())
        return seconds / Decimal(3600)


class MonitoringLog:
    """Every reading, kept in the order it was taken."""

    def __init__(self, readings: Iterable[Reading] = ()) -> None:
        self._readings: list[Reading] = []
        for reading in readings:
            self.record(reading)

    def record(self, reading: Reading) -> Reading:
        self._readings.append(reading)
        self._readings.sort()
        return reading

    def __len__(self) -> int:
        return len(self._readings)

    def __iter__(self) -> Iterator[Reading]:
        return iter(self._readings)

    def containers(self) -> tuple[str, ...]:
        return tuple(sorted({reading.container for reading in self._readings}))

    def for_container(self, container: str) -> tuple[Reading, ...]:
        code = normalise_code(container, field="container")
        return tuple(reading for reading in self._readings if reading.container == code)

    def within(self, window: DateRange) -> tuple[Reading, ...]:
        return tuple(reading for reading in self._readings if reading.taken_at.date() in window)

    def latest(self, container: str) -> Reading | None:
        readings = self.for_container(container)
        return readings[-1] if readings else None

    def mean_oxygen(self, container: str) -> Decimal:
        readings = self.for_container(container)
        if not readings:
            raise ValidationError("no readings for that unit", field="container")
        total = sum((reading.oxygen_mgL for reading in readings), Decimal(0))
        return total / Decimal(len(readings))

    def excursions(self, thresholds: Thresholds | None = None) -> tuple[Excursion, ...]:
        """Collapse consecutive bad readings into one excursion per unit and kind."""

        lines = thresholds or Thresholds()
        open_runs: dict[tuple[str, ExcursionKind], list[Reading]] = {}
        closed: list[Excursion] = []
        for reading in self._readings:
            breached = set(reading.breaches(lines))
            for key in list(open_runs):
                if key[0] != reading.container:
                    continue
                if key[1] not in breached:
                    closed.append(_close(key, open_runs.pop(key)))
            for kind in breached:
                open_runs.setdefault((reading.container, kind), []).append(reading)
        for key in list(open_runs):
            closed.append(_close(key, open_runs.pop(key)))
        closed.sort(key=lambda run: (run.started_at, run.container, run.kind.value))
        return tuple(closed)


def _close(key: tuple[str, ExcursionKind], readings: list[Reading]) -> Excursion:
    container, kind = key
    if kind is ExcursionKind.LOW_OXYGEN:
        worst = min(reading.oxygen_mgL for reading in readings)
    elif kind is ExcursionKind.HIGH_TEMPERATURE:
        worst = max(reading.celsius for reading in readings)
    else:
        worst = min(reading.celsius for reading in readings)
    return Excursion(
        container=container,
        kind=kind,
        started_at=readings[0].taken_at,
        ended_at=readings[-1].taken_at,
        worst=to_decimal(worst, field="worst"),
        readings=len(readings),
    )
