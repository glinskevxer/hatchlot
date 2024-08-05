"""Where a lot has got to, measured in degrees rather than days.

Three marks matter. Eye-up, when the pigment shows and the eggs can be handled
again. Hatch, when the alevins come out. Swim-up, when they are ready to be
ponded and start feeding. All three are counts of thermal units, so the calendar
date they land on is whatever the water decides.

The rule that governs the room is the tender period: from about a day after
fertilisation until eye-up, an egg that is jarred dies. So handling is refused
in that window, and that refusal is the reason the milestone maths has to be
right rather than approximately right.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from enum import Enum

from ..calendar import parse_date
from ..errors import PolicyError, ValidationError
from ..numeric import Number, to_decimal
from ..species import Species
from ..water.thermal import GapPolicy, ThermalSeries

# Thermal units after fertilisation for which an egg is still safe to move.
TENDER_START_UNITS = Decimal(24)


class Mark(Enum):
    """The three milestones of incubation."""

    EYE_UP = "eye_up"
    HATCH = "hatch"
    SWIM_UP = "swim_up"


@dataclass(frozen=True, slots=True)
class Milestone:
    """One mark: what it needs, when it landed or is expected to."""

    mark: Mark
    units_required: Decimal
    day: date | None
    projected: bool

    @property
    def is_reached(self) -> bool:
        return self.day is not None and not self.projected


def units_for(species: Species, mark: Mark) -> Decimal:
    """The thermal units a species needs to reach a mark."""

    return {
        Mark.EYE_UP: species.eye_up_units,
        Mark.HATCH: species.hatch_units,
        Mark.SWIM_UP: species.swim_up_units,
    }[mark]


def accumulated(
    series: ThermalSeries,
    spawned_on: object,
    as_of: object,
    species: Species,
    *,
    policy: GapPolicy = GapPolicy.CARRY_FORWARD,
) -> Decimal:
    """Thermal units a lot has taken on between the take and a day."""

    from ..calendar import DateRange

    start = parse_date(spawned_on, field="spawned_on")
    end = parse_date(as_of, field="as_of")
    if end < start:
        raise ValidationError("that is before the eggs were taken", field="as_of")
    return series.accumulate(
        DateRange(start, end), zero_point_c=species.zero_point_c, policy=policy
    )


def milestone(
    series: ThermalSeries,
    spawned_on: object,
    species: Species,
    mark: Mark,
    *,
    policy: GapPolicy = GapPolicy.CARRY_FORWARD,
    projection_celsius: Number | None = None,
) -> Milestone:
    """When a mark landed, or when it is expected to on a stated water.

    A mark the series has already passed comes back with `projected` false. One
    the series has not reached comes back projected off the temperature given,
    and refuses to guess if none was.
    """

    required = units_for(species, mark)
    start = parse_date(spawned_on, field="spawned_on")
    landed = series.day_units_reach(
        start, required, zero_point_c=species.zero_point_c, policy=policy
    )
    if landed is not None:
        return Milestone(mark=mark, units_required=required, day=landed, projected=False)
    if projection_celsius is None:
        return Milestone(mark=mark, units_required=required, day=None, projected=True)
    covered = series.covered
    if covered is None:
        anchor = start
        so_far = Decimal(0)
    else:
        anchor = max(covered.end, start)
        so_far = accumulated(series, start, anchor, species, policy=policy)
    remaining = required - so_far
    if remaining <= 0:
        return Milestone(mark=mark, units_required=required, day=anchor, projected=False)
    projected_day = series.projected_day(
        anchor, remaining, projection_celsius, zero_point_c=species.zero_point_c
    )
    return Milestone(mark=mark, units_required=required, day=projected_day, projected=True)


def all_milestones(
    series: ThermalSeries,
    spawned_on: object,
    species: Species,
    *,
    policy: GapPolicy = GapPolicy.CARRY_FORWARD,
    projection_celsius: Number | None = None,
) -> tuple[Milestone, ...]:
    """Every mark for a lot, in the order they happen."""

    return tuple(
        milestone(
            series,
            spawned_on,
            species,
            mark,
            policy=policy,
            projection_celsius=projection_celsius,
        )
        for mark in Mark
    )


def is_tender(units: Number, species: Species) -> bool:
    """Whether a lot at this accumulation is inside the window that cannot be moved."""

    taken = to_decimal(units, field="units")
    if taken < 0:
        raise ValidationError("thermal units cannot be negative", field="units")
    return TENDER_START_UNITS <= taken < species.eye_up_units


def check_handling(units: Number, species: Species) -> None:
    """Refuse a movement inside the tender window, with the rule named."""

    if is_tender(units, species):
        raise PolicyError(
            f"a lot at {to_decimal(units)} units is tender until {species.eye_up_units}",
            rule="incubation.tender",
        )


def development_stage(units: Number, species: Species) -> Mark | None:
    """The last mark a lot has passed, or None if it has passed none."""

    taken = to_decimal(units, field="units")
    passed = [mark for mark in Mark if taken >= units_for(species, mark)]
    return passed[-1] if passed else None
