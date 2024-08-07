"""Shocking, and the count everything downstream is really based on.

At eye-up the lot is jarred on purpose. Eggs that were never fertilised, or that
died early and have not shown it yet, go white within a day and get picked out.
What is left is the eyed count, and that number is the one a hatchery ships
against, plans against and gets audited on. The green count off the take was
always an estimate with a method attached; the eyed count is close to real.

Shocking before eye-up kills the lot, so it is refused rather than warned about.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from ..calendar import parse_date
from ..errors import PolicyError, StateError, ValidationError
from ..numeric import Number, require_non_negative, require_positive, safe_divide
from ..species import Species
from .development import check_handling
from .eggslot import EggLot, EggStage, LossCause


@dataclass(frozen=True, slots=True)
class ShockResult:
    """What came out of a shock: the eyed count and what it cost."""

    day: date
    before: Decimal
    eyed: Decimal
    whites: Decimal

    @property
    def eye_up_rate(self) -> Decimal:
        """The share of the standing count that eyed up."""

        return safe_divide(self.eyed, self.before, field="before")

    @property
    def white_rate(self) -> Decimal:
        return safe_divide(self.whites, self.before, field="before")


def shock(
    lot: EggLot,
    day: object,
    eyed_count: Number,
    species: Species,
    units_accumulated: Number,
) -> ShockResult:
    """Shock a lot, book the whites, and leave the eyed count standing.

    The eyed count is what the crew counted. The whites are the difference, so a
    count above what the lot is holding is refused rather than quietly clamped.
    """

    if lot.stage is not EggStage.GREEN:
        raise StateError(f"lot {lot.code} is {lot.stage.value} and has been shocked already")
    check_handling(units_accumulated, species)
    if require_non_negative(units_accumulated, field="units") < species.eye_up_units:
        raise PolicyError(
            f"lot {lot.code} is at {units_accumulated} units and eyes up at {species.eye_up_units}",
            rule="incubation.shock_too_early",
        )
    standing = lot.count
    eyed = require_non_negative(eyed_count, field="eyed_count")
    if eyed > standing:
        raise ValidationError(
            f"an eyed count of {eyed} is more than the {standing} standing", field="eyed_count"
        )
    when = parse_date(day)
    whites = standing - eyed
    if whites > 0:
        lot.record_loss(when, whites, LossCause.SHOCK)
    lot.advance(EggStage.EYED)
    return ShockResult(day=when, before=standing, eyed=eyed, whites=whites)


def fertility(result: ShockResult, green_count: Number) -> Decimal:
    """The share of the green count that turned out to be viable.

    Not the same as the eye-up rate, which is against the count still standing
    at the shock. This is the number the spawning crew is judged on.
    """

    green = require_positive(green_count, field="green_count")
    return safe_divide(result.eyed, green, field="green_count")


def expected_whites(green_count: Number, expected_fertility: Number = "0.9") -> Decimal:
    """How many whites a normal shock should produce, for a crew to work against."""

    green = require_positive(green_count, field="green_count")
    share = require_non_negative(expected_fertility, field="expected_fertility")
    if share > 1:
        raise ValidationError("a fertility over one is not a fertility", field="expected_fertility")
    return green * (Decimal(1) - share)


def is_shock_plausible(result: ShockResult, green_count: Number, *, floor: Number = "0.5") -> bool:
    """Whether a shock result is believable or wants a recount.

    A fertility under the floor is usually a counting mistake rather than a
    biological disaster, and the point of this is to make somebody check before
    the number goes into the inventory.
    """

    return fertility(result, green_count) >= require_non_negative(floor, field="floor")
