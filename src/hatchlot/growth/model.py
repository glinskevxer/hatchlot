"""The growth model, which is a cube root and a temperature sum.

Fish do not grow at a percent a day. They grow so that the cube root of the
weight rises in a straight line against accumulated temperature, and the slope
of that line is the thermal growth coefficient. That one idea is what lets a
hatchery say in October what size the fish will be in April, on water it has not
seen yet.

The specific growth rate is here too because everyone quotes it, but it is a
worse predictor and the reason is written down: it falls as the fish grow, so a
figure fitted on fry does not survive to smolts.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from ..errors import ValidationError
from ..numeric import Number, require_positive, to_decimal
from ..quantities.base import Quantity

THIRD = Decimal(1) / Decimal(3)


def cube_root(value: Number) -> Decimal:
    """Cube root of a positive number, in Decimal so a report can print it."""

    number = require_positive(value, field="value")
    return number**THIRD


@dataclass(frozen=True, slots=True)
class GrowthModel:
    """A thermal growth coefficient, and the water it was fitted on."""

    coefficient: Decimal
    fitted_on_days: int = 0

    def __post_init__(self) -> None:
        require_positive(self.coefficient, field="coefficient")
        if self.fitted_on_days < 0:
            raise ValidationError("a fit cannot run for negative days", field="fitted_on_days")

    def grow(self, weight: Quantity, thermal_units: Number) -> Quantity:
        """The weight a fish reaches after taking on thermal units."""

        units = to_decimal(thermal_units, field="thermal_units")
        if units < 0:
            raise ValidationError("thermal units cannot be negative", field="thermal_units")
        grams = require_positive(weight.to("g").amount, field="weight")
        end = cube_root(grams) + self.coefficient / Decimal(1000) * units
        if end <= 0:
            raise ValidationError("that would shrink the fish away", field="thermal_units")
        return Quantity(end**3, "g")

    def units_to_reach(self, start: Quantity, target: Quantity) -> Decimal:
        """The thermal units needed to get from one weight to another."""

        from_grams = require_positive(start.to("g").amount, field="start")
        to_grams = require_positive(target.to("g").amount, field="target")
        if to_grams <= from_grams:
            raise ValidationError("the target is not bigger than the start", field="target")
        return (cube_root(to_grams) - cube_root(from_grams)) * Decimal(1000) / self.coefficient

    def days_to_reach(self, start: Quantity, target: Quantity, mean_celsius: Number) -> int:
        """Days at a steady temperature to get from one weight to another."""

        water = require_positive(mean_celsius, field="mean_celsius")
        units = self.units_to_reach(start, target)
        return int((units / water).to_integral_value(rounding="ROUND_CEILING"))


def fit_coefficient(start: Quantity, end: Quantity, thermal_units: Number) -> GrowthModel:
    """Fit a coefficient from a lot that actually grew."""

    units = require_positive(thermal_units, field="thermal_units")
    from_grams = require_positive(start.to("g").amount, field="start")
    to_grams = require_positive(end.to("g").amount, field="end")
    if to_grams <= from_grams:
        raise ValidationError("the fish did not grow", field="end")
    coefficient = (cube_root(to_grams) - cube_root(from_grams)) * Decimal(1000) / units
    return GrowthModel(coefficient=coefficient, fitted_on_days=0)


def specific_growth_rate(start: Quantity, end: Quantity, days: int) -> Decimal:
    """Percent of body weight gained per day, the figure everybody quotes.

    It is not constant across a rearing cycle, which is exactly why the growth
    model above is not built on it.
    """

    if days < 1:
        raise ValidationError("a growth rate needs days", field="days")
    from_grams = require_positive(start.to("g").amount, field="start")
    to_grams = require_positive(end.to("g").amount, field="end")
    ratio = to_grams / from_grams
    return (ratio ** (Decimal(1) / Decimal(days)) - Decimal(1)) * Decimal(100)


def weight_after_days(
    model: GrowthModel, weight: Quantity, mean_celsius: Number, days: int
) -> Quantity:
    """Where a lot gets to in a stated number of days on a stated water."""

    if days < 0:
        raise ValidationError("cannot grow backwards", field="days")
    water = require_positive(mean_celsius, field="mean_celsius")
    return model.grow(weight, water * Decimal(days))


def condition_length(weight: Quantity, condition_factor: Number) -> Quantity:
    """Length in inches off a weight, through a hatchery condition factor."""

    pounds = require_positive(weight.to("lb").amount, field="weight")
    factor = require_positive(condition_factor, field="condition_factor")
    return Quantity((pounds / factor) ** THIRD, "in")
