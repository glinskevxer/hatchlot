"""How much to feed, which is a table with two ways in.

Feeding rate falls as the fish grow and rises as the water warms, so the chart on
the feed room wall is a grid with fish size down one side and temperature across
the top. This is that grid, read with interpolation on both axes so a lot at
three and a half grams on eleven degree water gets an answer rather than the
nearest row.

Everything comes back as a share of body weight per day. Turning that into
kilograms is the caller's job, because the biomass is the caller's number and
this module should not be able to get it wrong.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from ..errors import ValidationError
from ..numeric import Number, interpolate, require_positive, to_decimal
from ..quantities.base import Quantity
from ..quantities.temperature import Temperature

# Fish weights in grams down the side, water temperatures in Celsius across the
# top, percent of body weight per day in the cells. The shape of a standard
# coldwater feeding chart, trimmed to the range a salmonid hatchery works in.
_WEIGHTS = [Decimal(x) for x in ("0.3", "1", "3", "10", "30", "100")]
_TEMPERATURES = [Decimal(x) for x in ("4", "7", "10", "13", "16")]
_TABLE: list[list[str]] = [
    ["3.4", "4.6", "6.0", "7.2", "7.8"],
    ["2.4", "3.3", "4.3", "5.2", "5.6"],
    ["1.7", "2.3", "3.0", "3.6", "3.9"],
    ["1.2", "1.6", "2.1", "2.5", "2.7"],
    ["0.8", "1.1", "1.4", "1.7", "1.9"],
    ["0.5", "0.7", "0.9", "1.1", "1.2"],
]


def _bracket(values: list[Decimal], target: Decimal) -> tuple[int, int]:
    """The two rows a value sits between, clamped at the ends of the table."""

    if target <= values[0]:
        return 0, 0
    if target >= values[-1]:
        return len(values) - 1, len(values) - 1
    for index in range(len(values) - 1):
        if values[index] <= target <= values[index + 1]:
            return index, index + 1
    return len(values) - 1, len(values) - 1


def feeding_rate(weight: Quantity, water: Temperature) -> Decimal:
    """Percent of body weight per day for a fish of a size on a water."""

    grams = require_positive(weight.to("g").amount, field="weight")
    celsius = water.celsius
    low_w, high_w = _bracket(_WEIGHTS, grams)
    low_t, high_t = _bracket(_TEMPERATURES, celsius)

    def cell(row: int, column: int) -> Decimal:
        return Decimal(_TABLE[row][column])

    if low_t == high_t:
        top = cell(low_w, low_t)
        bottom = cell(high_w, low_t)
    else:
        top = interpolate(
            celsius,
            _TEMPERATURES[low_t],
            cell(low_w, low_t),
            _TEMPERATURES[high_t],
            cell(low_w, high_t),
        )
        bottom = interpolate(
            celsius,
            _TEMPERATURES[low_t],
            cell(high_w, low_t),
            _TEMPERATURES[high_t],
            cell(high_w, high_t),
        )
    if low_w == high_w:
        return top
    return interpolate(grams, _WEIGHTS[low_w], top, _WEIGHTS[high_w], bottom)


def daily_ration(biomass: Quantity, rate_percent: Number) -> Quantity:
    """The feed a biomass is owed for a day at a rate."""

    share = to_decimal(rate_percent, field="rate_percent")
    if share < 0:
        raise ValidationError("a feeding rate cannot be negative", field="rate_percent")
    kilograms = biomass.to("kg").amount
    if kilograms < 0:
        raise ValidationError("a biomass cannot be negative", field="biomass")
    return Quantity(kilograms * share / Decimal(100), "kg")


def ration_for(biomass: Quantity, weight: Quantity, water: Temperature) -> Quantity:
    """The feed a lot is owed for a day, straight off the chart."""

    return daily_ration(biomass, feeding_rate(weight, water))


def feeds_per_day(weight: Quantity) -> int:
    """How many times a day fish of a size should be fed.

    Small fish have no stomach to speak of and are fed constantly; big fish are
    fed twice. The steps are the ones a hatchery actually works to.
    """

    grams = require_positive(weight.to("g").amount, field="weight")
    if grams < Decimal(1):
        return 8
    if grams < Decimal(5):
        return 6
    if grams < Decimal(20):
        return 4
    if grams < Decimal(60):
        return 3
    return 2


def per_feeding(ration: Quantity, weight: Quantity) -> Quantity:
    """The ration split across the day's feedings."""

    return Quantity(ration.to("kg").amount / Decimal(feeds_per_day(weight)), "kg")


@dataclass(frozen=True, slots=True)
class RationPlan:
    """What a lot should be fed over a stretch, and what it comes to."""

    lot: str
    days: int
    rate_percent: Decimal
    daily: Quantity
    feedings: int

    @property
    def total(self) -> Quantity:
        return Quantity(self.daily.to("kg").amount * Decimal(self.days), "kg")

    @property
    def per_feeding(self) -> Quantity:
        return Quantity(self.daily.to("kg").amount / Decimal(self.feedings), "kg")


def plan_ration(
    lot: str, biomass: Quantity, weight: Quantity, water: Temperature, days: int
) -> RationPlan:
    """Work a lot's feeding out for a stretch of days on one water."""

    if days < 1:
        raise ValidationError("a plan covers at least a day", field="days")
    rate = feeding_rate(weight, water)
    return RationPlan(
        lot=lot,
        days=days,
        rate_percent=rate,
        daily=daily_ration(biomass, rate),
        feedings=feeds_per_day(weight),
    )
