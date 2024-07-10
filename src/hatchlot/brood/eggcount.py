"""Counting eggs without counting eggs.

Nobody counts a take one egg at a time. Three methods stand in for it, and they
disagree by a few percent on the same lot, which is why the method used has to
travel with the number.

The von Bayer method lays eggs in a trough and counts how many fit in twelve
inches, which gives an egg diameter and from that a count per unit volume.
Displacement measures the volume the eggs push aside. Gravimetric weighs a
counted sample and scales. The packing fraction is the one fitted constant in
here and it is exposed, because a station with its own trough should use its own.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum

from ..errors import ValidationError
from ..numeric import Number, percent_difference, require_positive, to_decimal
from ..quantities.base import Quantity

# Loose random packing of spheres, trimmed for the way water eggs sit together.
PACKING_FRACTION = Decimal("0.62")
PI = Decimal("3.14159265358979")


class CountMethod(Enum):
    """How a number of eggs was arrived at."""

    VON_BAYER = "von_bayer"
    DISPLACEMENT = "displacement"
    GRAVIMETRIC = "gravimetric"
    ENUMERATED = "enumerated"

    @property
    def is_estimate(self) -> bool:
        return self is not CountMethod.ENUMERATED


def egg_diameter(eggs_in_twelve_inches: Number) -> Quantity:
    """Egg diameter from a von Bayer trough count."""

    count = require_positive(eggs_in_twelve_inches, field="eggs_in_twelve_inches")
    return Quantity(Decimal(12) / count, "in")


def egg_volume(diameter: Quantity) -> Quantity:
    """The volume of one egg, treated as a sphere."""

    millimetres = require_positive(diameter.to("mm").amount, field="diameter")
    cubic_mm = PI * millimetres**3 / Decimal(6)
    return Quantity(cubic_mm / Decimal(1_000_000), "L")


def eggs_per_litre(diameter: Quantity, *, packing_fraction: Number = PACKING_FRACTION) -> Decimal:
    """How many eggs of a diameter fill a litre, allowing for the gaps."""

    packing = require_positive(packing_fraction, field="packing_fraction")
    if packing > 1:
        raise ValidationError("a packing fraction cannot exceed one", field="packing_fraction")
    single = egg_volume(diameter).amount
    return packing / single


def von_bayer_count(
    eggs_in_twelve_inches: Number,
    volume: Quantity,
    *,
    packing_fraction: Number = PACKING_FRACTION,
) -> Decimal:
    """Eggs in a measured volume, from a trough count."""

    per_litre = eggs_per_litre(
        egg_diameter(eggs_in_twelve_inches), packing_fraction=packing_fraction
    )
    litres = require_positive(volume.to("L").amount, field="volume")
    return per_litre * litres


def displacement_count(displaced: Quantity, diameter: Quantity) -> Decimal:
    """Eggs from the water they push out of a graduated cylinder.

    Displacement measures the eggs themselves rather than the eggs and the gaps
    between them, so no packing fraction belongs in here. That is exactly why
    this method and the trough method disagree on the same lot.
    """

    litres = require_positive(displaced.to("L").amount, field="displaced")
    return litres / egg_volume(diameter).amount


def gravimetric_count(sample_count: Number, sample_weight: Quantity, total: Quantity) -> Decimal:
    """Eggs in a whole take from a counted and weighed sample."""

    counted = require_positive(sample_count, field="sample_count")
    sample_grams = require_positive(sample_weight.to("g").amount, field="sample_weight")
    total_grams = require_positive(total.to("g").amount, field="total")
    return counted / sample_grams * total_grams


@dataclass(frozen=True, slots=True)
class EggEstimate:
    """A count, how it was got, and what it is worth."""

    eggs: Decimal
    method: CountMethod

    def __init__(self, eggs: Number, method: CountMethod) -> None:
        if not isinstance(method, CountMethod):
            raise ValidationError(f"{method!r} is not a count method", field="method")
        object.__setattr__(self, "eggs", require_positive(eggs, field="eggs"))
        object.__setattr__(self, "method", method)

    @property
    def rounded(self) -> int:
        """The whole eggs that go on the form."""

        return int(self.eggs.to_integral_value(rounding="ROUND_HALF_UP"))

    def agrees_with(self, other: EggEstimate, *, tolerance_percent: Number = 5) -> bool:
        """Whether two methods landed close enough to trust either."""

        allowed = require_positive(tolerance_percent, field="tolerance_percent")
        difference = abs(percent_difference(self.eggs, other.eggs))
        return difference <= allowed


def reconcile(estimates: list[EggEstimate], *, tolerance_percent: Number = 5) -> EggEstimate:
    """Pick the number that goes on the form when two methods were run.

    An enumerated count wins outright. Otherwise the estimates have to agree
    inside the tolerance, and the mean of them is what gets recorded, because
    picking the bigger one is how a hatchery talks itself into an inventory it
    does not have.
    """

    if not estimates:
        raise ValidationError("no estimates to reconcile", field="estimates")
    exact = [estimate for estimate in estimates if not estimate.method.is_estimate]
    if exact:
        return exact[0]
    if len(estimates) == 1:
        return estimates[0]
    tolerance = to_decimal(tolerance_percent, field="tolerance_percent")
    lowest = min(estimate.eggs for estimate in estimates)
    highest = max(estimate.eggs for estimate in estimates)
    if abs(percent_difference(highest, lowest)) > tolerance:
        raise ValidationError(
            f"the estimates differ by more than {tolerance} percent", field="estimates"
        )
    total = sum((estimate.eggs for estimate in estimates), Decimal(0))
    return EggEstimate(total / Decimal(len(estimates)), estimates[0].method)
