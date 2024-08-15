"""The incubation room's calendar, worked out rather than typed in.

Nobody writes a hatchery schedule down, because the water writes it. What a
manager wants is the list of what is coming: which lots shock this month, which
hatch over the holiday, and how much of that lands in one week. All of it falls
out of the milestone maths, so this module is a join and a sort rather than
anything new.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from ..calendar import DateRange, parse_date
from ..errors import ValidationError
from ..numeric import Number
from ..species import Species, species
from ..water.thermal import GapPolicy, ThermalSeries
from .development import Mark, all_milestones
from .eggslot import EggLot


@dataclass(frozen=True, slots=True, order=True)
class ScheduleEntry:
    """One thing that is going to happen to one lot."""

    day: date
    lot: str
    mark: Mark
    eggs: Decimal
    projected: bool

    @property
    def label(self) -> str:
        tail = " (projected)" if self.projected else ""
        return f"{self.day.isoformat()} {self.lot} {self.mark.value}{tail}"


def schedule_for(
    lot: EggLot,
    series: ThermalSeries,
    *,
    stock: Species | None = None,
    policy: GapPolicy = GapPolicy.CARRY_FORWARD,
    projection_celsius: Number | None = None,
) -> tuple[ScheduleEntry, ...]:
    """Every mark still to come, or already passed, for one lot."""

    kind = stock or species(lot.species)
    entries = []
    for found in all_milestones(
        series,
        lot.spawned_on,
        kind,
        policy=policy,
        projection_celsius=projection_celsius,
    ):
        if found.day is None:
            continue
        entries.append(
            ScheduleEntry(
                day=found.day,
                lot=str(lot.code),
                mark=found.mark,
                eggs=lot.count,
                projected=found.projected,
            )
        )
    return tuple(sorted(entries))


def room_schedule(
    lots: list[EggLot],
    series: ThermalSeries,
    *,
    policy: GapPolicy = GapPolicy.CARRY_FORWARD,
    projection_celsius: Number | None = None,
) -> tuple[ScheduleEntry, ...]:
    """The whole room's calendar, in the order it happens."""

    entries: list[ScheduleEntry] = []
    for lot in lots:
        if lot.stage.is_closed:
            continue
        entries.extend(
            schedule_for(lot, series, policy=policy, projection_celsius=projection_celsius)
        )
    return tuple(sorted(entries))


def within(entries: tuple[ScheduleEntry, ...], window: DateRange) -> tuple[ScheduleEntry, ...]:
    return tuple(entry for entry in entries if entry.day in window)


def of_mark(entries: tuple[ScheduleEntry, ...], mark: Mark) -> tuple[ScheduleEntry, ...]:
    return tuple(entry for entry in entries if entry.mark is mark)


def next_after(entries: tuple[ScheduleEntry, ...], day: object) -> ScheduleEntry | None:
    """The next thing that happens after a day, or None if the list runs out."""

    when = parse_date(day)
    later = [entry for entry in entries if entry.day > when]
    return min(later) if later else None


def busiest_week(entries: tuple[ScheduleEntry, ...]) -> DateRange | None:
    """The seven day window with the most eggs moving through it.

    Weighted by eggs rather than by number of lots, because two jars of a
    thousand is not the week that needs the extra hands.
    """

    if not entries:
        return None
    best: DateRange | None = None
    best_eggs = Decimal(-1)
    for entry in entries:
        window = DateRange(entry.day, entry.day.fromordinal(entry.day.toordinal() + 6))
        eggs = sum((other.eggs for other in entries if other.day in window), Decimal(0))
        if eggs > best_eggs:
            best_eggs = eggs
            best = window
    return best


def workload(entries: tuple[ScheduleEntry, ...], window: DateRange) -> dict[Mark, Decimal]:
    """Eggs by mark inside a window, which is the crewing question."""

    if window.days > 400:
        raise ValidationError("that is not a planning window", field="window")
    totals: dict[Mark, Decimal] = {}
    for entry in within(entries, window):
        totals[entry.mark] = totals.get(entry.mark, Decimal(0)) + entry.eggs
    return totals
