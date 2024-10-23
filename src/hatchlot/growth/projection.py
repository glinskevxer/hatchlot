"""Projecting a lot forward, and answering the release date question.

Two questions get asked all year and they are the same arithmetic run in
opposite directions. Given the water we expect, how big will these fish be on
the release date. And given the size we have promised, when will they get there.

Both need a temperature the water has not reached yet, so both answers carry the
assumption they were made under. A projection that does not say what water it
assumed is a number somebody will quote back in April.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from ..calendar import DateRange, parse_date
from ..errors import ValidationError
from ..numeric import Number, require_positive, to_decimal
from ..quantities.base import Quantity
from ..water.thermal import GapPolicy, ThermalSeries
from .model import GrowthModel


@dataclass(frozen=True, slots=True)
class Projection:
    """Where a lot is expected to get to, and what that assumed."""

    start_day: date
    start_weight: Quantity
    end_day: date
    end_weight: Quantity
    thermal_units: Decimal
    assumed_celsius: Decimal | None

    @property
    def days(self) -> int:
        return (self.end_day - self.start_day).days

    @property
    def gain(self) -> Quantity:
        return self.end_weight - self.start_weight

    @property
    def is_measured(self) -> bool:
        """Whether the whole projection ran on water that was actually recorded."""

        return self.assumed_celsius is None

    def line(self) -> str:
        basis = "on the record" if self.is_measured else f"assuming {self.assumed_celsius} degC"
        return (
            f"{self.start_weight.rounded(2)} to {self.end_weight.rounded(2)} "
            f"over {self.days} days, {basis}"
        )


def project_to_date(
    model: GrowthModel,
    weight: Quantity,
    start: object,
    end: object,
    series: ThermalSeries,
    *,
    assumed_celsius: Number | None = None,
    policy: GapPolicy = GapPolicy.CARRY_FORWARD,
) -> Projection:
    """How big a lot gets by a date, using the record as far as it goes.

    Past the end of the series it uses the assumed temperature, and refuses if
    it needs one and was not given one.
    """

    first = parse_date(start, field="start")
    last = parse_date(end, field="end")
    if last < first:
        raise ValidationError("the end is before the start", field="end")
    covered = series.covered
    units = Decimal(0)
    assumed: Decimal | None = None
    if covered is not None and covered.end >= first:
        measured_end = min(covered.end, last)
        units += series.accumulate(DateRange(first, measured_end), policy=policy)
        remaining_from = measured_end + timedelta(days=1)
    else:
        remaining_from = first
    if remaining_from <= last:
        if assumed_celsius is None:
            raise ValidationError(
                "the record stops before that date and no water was assumed",
                field="assumed_celsius",
            )
        assumed = require_positive(assumed_celsius, field="assumed_celsius")
        units += assumed * Decimal((last - remaining_from).days + 1)
    return Projection(
        start_day=first,
        start_weight=weight,
        end_day=last,
        end_weight=model.grow(weight, units),
        thermal_units=units,
        assumed_celsius=assumed,
    )


def project_to_size(
    model: GrowthModel,
    weight: Quantity,
    target: Quantity,
    start: object,
    mean_celsius: Number,
) -> Projection:
    """When a lot reaches a size on a stated water."""

    water = require_positive(mean_celsius, field="mean_celsius")
    first = parse_date(start, field="start")
    units = model.units_to_reach(weight, target)
    days = int((units / water).to_integral_value(rounding="ROUND_CEILING"))
    return Projection(
        start_day=first,
        start_weight=weight,
        end_day=first + timedelta(days=days),
        end_weight=target,
        thermal_units=units,
        assumed_celsius=water,
    )


def meets_target(projection: Projection, target: Quantity, *, tolerance: Number = "0.05") -> bool:
    """Whether a projected size is close enough to a promised one."""

    allowed = to_decimal(tolerance, field="tolerance")
    if allowed < 0:
        raise ValidationError("a tolerance cannot be negative", field="tolerance")
    wanted = require_positive(target.to("g").amount, field="target")
    reached = projection.end_weight.to("g").amount
    return reached >= wanted * (Decimal(1) - allowed)


def required_temperature(
    model: GrowthModel, weight: Quantity, target: Quantity, start: object, end: object
) -> Decimal:
    """The mean water a lot would need to hit a size by a date.

    Answering this is how a manager finds out that the schedule needs a bigger
    fish at ponding rather than warmer water in March.
    """

    first = parse_date(start, field="start")
    last = parse_date(end, field="end")
    days = (last - first).days
    if days < 1:
        raise ValidationError("that is not a window to grow in", field="end")
    return model.units_to_reach(weight, target) / Decimal(days)
