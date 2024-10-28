"""Size spread in a lot, and whether grading it would pay.

Fish in one raceway are not one size. The spread matters because the big ones
eat first, so a lot that starts uneven gets more uneven, and because a release
target is a size not an average. Grading fixes it and costs a handling, so the
decision needs a number rather than a look down the raceway.

The number is the coefficient of variation of the individual weights. Under
about a tenth nobody grades. Over about a fifth everybody does.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from ..errors import ValidationError
from ..numeric import Number, require_positive, safe_divide, to_decimal
from ..quantities.base import Quantity


@dataclass(frozen=True, slots=True, order=True)
class SizeClass:
    """One grade: a name and the weight band that falls in it."""

    low_g: Decimal
    high_g: Decimal
    name: str

    def __init__(self, name: str, low: Quantity, high: Quantity) -> None:
        low_g = require_positive(low.to("g").amount, field="low")
        high_g = require_positive(high.to("g").amount, field="high")
        if high_g <= low_g:
            raise ValidationError("a size class runs from small to large", field="high")
        if not name.strip():
            raise ValidationError("a size class needs a name", field="name")
        object.__setattr__(self, "low_g", low_g)
        object.__setattr__(self, "high_g", high_g)
        object.__setattr__(self, "name", name.strip())

    def holds(self, weight: Quantity) -> bool:
        """Closed at the bottom, open at the top, so the bands tile cleanly."""

        grams = weight.to("g").amount
        return self.low_g <= grams < self.high_g


@dataclass(frozen=True, slots=True)
class Distribution:
    """The spread of individual weights in a sample."""

    count: int
    mean_g: Decimal
    spread_g: Decimal
    smallest_g: Decimal
    largest_g: Decimal

    @property
    def mean(self) -> Quantity:
        return Quantity(self.mean_g, "g")

    @property
    def coefficient_of_variation(self) -> Decimal:
        return safe_divide(self.spread_g, self.mean_g, field="mean")

    @property
    def range_ratio(self) -> Decimal:
        """Largest over smallest, which is what a crew sees in the net."""

        return safe_divide(self.largest_g, self.smallest_g, field="smallest")

    def is_uniform(self, *, limit: Number = "0.10") -> bool:
        return self.coefficient_of_variation <= to_decimal(limit, field="limit")

    def wants_grading(self, *, limit: Number = "0.20") -> bool:
        return self.coefficient_of_variation > to_decimal(limit, field="limit")


def describe(weights: list[Quantity]) -> Distribution:
    """Work the spread out of a set of individually weighed fish."""

    if len(weights) < 2:
        raise ValidationError("a distribution needs at least two fish", field="weights")
    grams = [require_positive(weight.to("g").amount, field="weight") for weight in weights]
    count = Decimal(len(grams))
    mean = sum(grams, Decimal(0)) / count
    variance = sum(((value - mean) ** 2 for value in grams), Decimal(0)) / count
    return Distribution(
        count=len(grams),
        mean_g=mean,
        spread_g=variance.sqrt(),
        smallest_g=min(grams),
        largest_g=max(grams),
    )


def grade(weights: list[Quantity], classes: list[SizeClass]) -> dict[str, int]:
    """Count a sample into size classes, with anything outside them counted too."""

    if not classes:
        raise ValidationError("no size classes to grade into", field="classes")
    ordered = sorted(classes)
    counts: dict[str, int] = {size.name: 0 for size in ordered}
    counts["ungraded"] = 0
    for weight in weights:
        for size in ordered:
            if size.holds(weight):
                counts[size.name] += 1
                break
        else:
            counts["ungraded"] += 1
    return counts


def graded_share(counts: dict[str, int], name: str) -> Decimal:
    """The share of a graded sample that fell in one class."""

    total = sum(counts.values())
    if total == 0:
        raise ValidationError("nothing was graded", field="counts")
    if name not in counts:
        raise ValidationError(f"{name!r} is not a class in this grading", field="name")
    return Decimal(counts[name]) / Decimal(total)


def split_at(distribution: Distribution, share: Number) -> Quantity:
    """The weight that would cut a lot into two parts of a stated share.

    A normal approximation, which is fine for the question it is asked for:
    where to set the bar on the grader.
    """

    fraction = to_decimal(share, field="share")
    if not 0 < fraction < 1:
        raise ValidationError("a split share is between zero and one", field="share")
    # z scores for the shares a hatchery actually grades at, interpolated
    # between rather than computed, because three decimal places is plenty.
    table = {
        Decimal("0.1"): Decimal("-1.282"),
        Decimal("0.25"): Decimal("-0.674"),
        Decimal("0.5"): Decimal(0),
        Decimal("0.75"): Decimal("0.674"),
        Decimal("0.9"): Decimal("1.282"),
    }
    keys = sorted(table)
    if fraction <= keys[0]:
        z = table[keys[0]]
    elif fraction >= keys[-1]:
        z = table[keys[-1]]
    else:
        z = Decimal(0)
        for low, high in zip(keys, keys[1:], strict=False):
            if low <= fraction <= high:
                span = high - low
                z = table[low] + (table[high] - table[low]) * (fraction - low) / span
                break
    grams = distribution.mean_g + z * distribution.spread_g
    if grams <= 0:
        raise ValidationError("that split falls below zero weight", field="share")
    return Quantity(grams, "g")
