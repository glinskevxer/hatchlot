"""How many eggs a female is expected to carry, and fitting that to a station.

Fecundity rises with the size of the fish, and the shape of that relation is a
power law: eggs go roughly with length cubed, which is to say with weight. Every
station has its own coefficients because its own fish are its own fish, so the
model is fitted from observed pairs rather than shipped as a constant.

Fitting is a plain least squares on the logs, which turns the power law into a
straight line. That is the whole trick and it is worth writing down, because the
residuals it reports are in log space and are not percentages.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from decimal import Decimal

from ..errors import ValidationError
from ..numeric import Number, percent_difference, require_positive, to_decimal
from ..quantities.base import Quantity


@dataclass(frozen=True, slots=True)
class FecundityModel:
    """`eggs = scale * length_cm ** exponent`, fitted or handed over."""

    scale: Decimal
    exponent: Decimal
    sample_size: int = 0

    def __post_init__(self) -> None:
        require_positive(self.scale, field="scale")
        require_positive(self.exponent, field="exponent")
        if self.sample_size < 0:
            raise ValidationError("a sample cannot be negative", field="sample_size")

    def expected(self, length: Quantity) -> Decimal:
        """Eggs expected of a female of this length."""

        centimetres = require_positive(length.to("cm").amount, field="length")
        eggs = float(self.scale) * math.pow(float(centimetres), float(self.exponent))
        return to_decimal(round(eggs, 2), field="eggs")

    def expected_total(self, lengths: list[Quantity]) -> Decimal:
        """What a pen of females is expected to give."""

        return sum((self.expected(length) for length in lengths), Decimal(0))

    def deviation(self, length: Quantity, observed: Number) -> Decimal:
        """How far an observed count sits from the model, in percent."""

        return percent_difference(
            require_positive(observed, field="observed"), self.expected(length)
        )

    def is_plausible(self, length: Quantity, observed: Number, *, tolerance: Number = 40) -> bool:
        """Whether a recorded count is close enough to the model to be believed."""

        allowed = require_positive(tolerance, field="tolerance")
        return abs(self.deviation(length, observed)) <= allowed


DEFAULT_MODEL = FecundityModel(scale=Decimal("0.0075"), exponent=Decimal("3.1"))


@dataclass(frozen=True, slots=True)
class Observation:
    """One female measured and her eggs counted."""

    length: Quantity
    eggs: Decimal

    def __init__(self, length: Quantity, eggs: Number) -> None:
        object.__setattr__(self, "length", length)
        object.__setattr__(self, "eggs", require_positive(eggs, field="eggs"))
        require_positive(length.to("cm").amount, field="length")


def fit(observations: list[Observation]) -> FecundityModel:
    """Fit the power law to observed pairs by least squares on the logs."""

    if len(observations) < 3:
        raise ValidationError("a fit needs at least three females", field="observations")
    xs = [math.log(float(o.length.to("cm").amount)) for o in observations]
    ys = [math.log(float(o.eggs)) for o in observations]
    n = float(len(observations))
    mean_x = sum(xs) / n
    mean_y = sum(ys) / n
    denominator = sum((x - mean_x) ** 2 for x in xs)
    if denominator == 0:
        raise ValidationError("every female is the same length", field="observations")
    slope = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys, strict=True)) / denominator
    intercept = mean_y - slope * mean_x
    if slope <= 0:
        raise ValidationError("these females get less fecund as they grow", field="observations")
    return FecundityModel(
        scale=to_decimal(round(math.exp(intercept), 8), field="scale"),
        exponent=to_decimal(round(slope, 6), field="exponent"),
        sample_size=len(observations),
    )


def residual_spread(model: FecundityModel, observations: list[Observation]) -> Decimal:
    """Mean absolute deviation of the observations from a model, in percent."""

    if not observations:
        raise ValidationError("no observations to score", field="observations")
    total = sum((abs(model.deviation(o.length, o.eggs)) for o in observations), Decimal(0))
    return total / Decimal(len(observations))


def females_needed(model: FecundityModel, target_eggs: Number, mean_length: Quantity) -> int:
    """How many females of an average size a target take needs, rounded up."""

    target = require_positive(target_eggs, field="target_eggs")
    each = model.expected(mean_length)
    return int((target / each).to_integral_value(rounding="ROUND_CEILING"))
