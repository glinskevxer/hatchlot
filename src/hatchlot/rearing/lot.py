"""The rearing lot: a population of fish with a size, sitting somewhere.

Everything a hatchery does after ponding is done to a lot. The lot carries the
number of fish and the mean weight, and every other number worth having is
derived from those two: biomass, fish per pound, the length that the loading
indices need, and the feed the lot is owed tomorrow.

Fish per pound is the unit a hatchery actually talks in, so it is a property
here rather than something each caller works out and rounds differently.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from enum import Enum

from ..calendar import parse_date
from ..errors import StateError, ValidationError
from ..identifiers import LotCode, normalise_code
from ..numeric import (
    Number,
    require_non_negative,
    require_positive,
    safe_divide,
    to_decimal,
)
from ..quantities.base import Quantity
from ..species import Species, species


class LotState(Enum):
    """Where a rearing lot is in its life."""

    REARING = "rearing"
    HELD = "held"
    RELEASED = "released"
    LOST = "lost"

    @property
    def is_closed(self) -> bool:
        return self in {LotState.RELEASED, LotState.LOST}


# The length weight relation a hatchery uses to turn a weight into the length
# the loading indices are written on: weight in pounds is the condition factor
# times length in inches cubed.
LENGTH_EXPONENT = Decimal(3)


@dataclass
class RearingLot:
    """A population of one species and size, in one container."""

    code: LotCode
    container: str
    ponded_on: date
    population: Decimal
    mean_weight: Quantity
    state: LotState = LotState.REARING
    origin_egg_lot: str = ""
    marks: list[str] = field(default_factory=list)
    note: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.code, LotCode):
            raise ValidationError("a rearing lot needs a lot code", field="code")
        self.container = normalise_code(self.container, field="container")
        self.ponded_on = parse_date(self.ponded_on)
        # A live lot has fish in it. A closed one has none, by definition, and it
        # still has to be loadable out of the database afterwards.
        if self.state.is_closed:
            self.population = require_non_negative(self.population, field="population")
        else:
            self.population = require_positive(self.population, field="population")
        require_positive(self.mean_weight.to("g").amount, field="mean_weight")
        if self.origin_egg_lot:
            self.origin_egg_lot = normalise_code(self.origin_egg_lot, field="origin_egg_lot")

    @property
    def species(self) -> Species:
        return species(self.code.species)

    @property
    def biomass(self) -> Quantity:
        return Quantity(self.population * self.mean_weight.to("kg").amount, "kg")

    @property
    def fish_per_pound(self) -> Decimal:
        """The number every hatchery conversation is held in."""

        return safe_divide(1, self.mean_weight.to("lb").amount, field="mean_weight")

    @property
    def length(self) -> Quantity:
        """Length off the weight through the species condition factor.

        The factor is the hatchery form of it, pounds over inches cubed, so the
        arithmetic happens in those units whatever the station reports in.
        """

        pounds = self.mean_weight.to("lb").amount
        factor = self.species.condition_factor
        inches = (pounds / factor) ** (Decimal(1) / LENGTH_EXPONENT)
        return Quantity(inches, "in")

    def days_reared(self, as_of: object) -> int:
        day = parse_date(as_of)
        if day < self.ponded_on:
            raise ValidationError("that is before the lot was ponded", field="as_of")
        return (day - self.ponded_on).days

    def remove(self, count: Number, *, reason: str = "") -> Decimal:
        """Take fish off the lot, refusing more than are there."""

        if self.state.is_closed:
            raise StateError(f"lot {self.code} is {self.state.value}")
        amount = require_positive(count, field="count")
        if amount > self.population:
            raise ValidationError(
                f"cannot remove {amount} from a lot of {self.population}", field="count"
            )
        self.population -= amount
        if reason:
            self.note = reason
        if self.population == 0:
            self.state = LotState.LOST if reason else LotState.RELEASED
        return self.population

    def add(self, count: Number, weight: Quantity | None = None) -> Decimal:
        """Put fish on the lot, blending the mean weight if one is given."""

        if self.state.is_closed:
            raise StateError(f"lot {self.code} is {self.state.value}")
        amount = require_positive(count, field="count")
        if weight is not None:
            require_positive(weight.to("g").amount, field="weight")
            total = (
                self.population * self.mean_weight.to("g").amount + amount * weight.to("g").amount
            )
            self.mean_weight = Quantity(total / (self.population + amount), "g")
        self.population += amount
        return self.population

    def resize(self, mean_weight: Quantity) -> Quantity:
        """Record a new mean weight off a sample."""

        require_positive(mean_weight.to("g").amount, field="mean_weight")
        self.mean_weight = mean_weight
        return self.mean_weight

    def move_to(self, container: str) -> str:
        if self.state.is_closed:
            raise StateError(f"lot {self.code} is {self.state.value} and does not move")
        self.container = normalise_code(container, field="container")
        return self.container

    def hold(self, reason: str) -> None:
        """Stop a lot going anywhere, which a treatment or a screen does."""

        if not reason.strip():
            raise ValidationError("a hold needs a reason", field="reason")
        if self.state.is_closed:
            raise StateError(f"lot {self.code} is {self.state.value}")
        self.state = LotState.HELD
        self.note = reason.strip()

    def release_hold(self) -> None:
        if self.state is not LotState.HELD:
            raise StateError(f"lot {self.code} is not held")
        self.state = LotState.REARING
        self.note = ""

    def add_mark(self, mark: str) -> str:
        code = normalise_code(mark, field="mark")
        if code in self.marks:
            raise ValidationError(f"{code} is already on this lot", field="mark")
        self.marks.append(code)
        return code


def total_population(lots: list[RearingLot]) -> Decimal:
    return sum((lot.population for lot in lots if not lot.state.is_closed), Decimal(0))


def total_biomass(lots: list[RearingLot], symbol: str = "kg") -> Quantity:
    total = Quantity(0, symbol)
    for lot in lots:
        if not lot.state.is_closed:
            total = total + lot.biomass
    return total


def weighted_mean_weight(lots: list[RearingLot], symbol: str = "g") -> Quantity:
    """The mean weight across lots, weighted by how many fish are in each."""

    live = [lot for lot in lots if not lot.state.is_closed]
    if not live:
        raise ValidationError("no live lots to average", field="lots")
    population = total_population(live)
    if population == 0:
        raise ValidationError("no fish to average", field="lots")
    total = sum((lot.population * lot.mean_weight.to(symbol).amount for lot in live), Decimal(0))
    return Quantity(to_decimal(total) / population, symbol)
