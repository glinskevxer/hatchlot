"""What a lot actually did, against what the model said it would.

A growth model is only worth having if somebody checks it. This keeps the sample
weights a lot has been given over a season, works out the coefficient the lot is
really growing at, and says whether it is tracking the plan or has stalled.

A stall is the useful output. Fish stop growing for reasons that show up nowhere
else for weeks: a feeder set wrong, a pathogen nobody has looked for yet, water
that is colder than the plan assumed.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from ..calendar import DateRange, parse_date
from ..errors import ValidationError
from ..identifiers import normalise_code
from ..journal import JournalLog
from ..numeric import Number, percent_difference, require_positive, to_decimal
from ..quantities.base import Quantity
from ..water.thermal import GapPolicy, ThermalSeries
from .model import GrowthModel, fit_coefficient


@dataclass(frozen=True, slots=True, order=True)
class WeighIn:
    """One recorded mean weight for a lot on a day."""

    day: date
    lot: str
    weight: Quantity

    def __init__(self, day: object, lot: str, weight: Quantity) -> None:
        object.__setattr__(self, "day", parse_date(day))
        object.__setattr__(self, "lot", normalise_code(lot, field="lot"))
        require_positive(weight.to("g").amount, field="weight")
        object.__setattr__(self, "weight", weight)


class GrowthHistory(JournalLog[WeighIn]):
    """Every weigh-in, over every lot."""

    def __init__(self) -> None:
        super().__init__(lambda entry: entry.day, lambda entry: entry.lot)

    def for_lot(self, lot: str) -> tuple[WeighIn, ...]:
        return self._for_key(lot)

    def latest_weight(self, lot: str) -> Quantity | None:
        entries = self.for_lot(lot)
        return entries[-1].weight if entries else None

    def span_for(self, lot: str) -> DateRange | None:
        entries = self.for_lot(lot)
        if len(entries) < 2:
            return None
        return DateRange(entries[0].day, entries[-1].day)

    def observed_model(self, lot: str, series: ThermalSeries) -> GrowthModel:
        """The coefficient the lot has really been growing at."""

        window = self.span_for(lot)
        if window is None:
            raise ValidationError("a lot needs two weigh-ins to fit", field="lot")
        entries = self.for_lot(lot)
        units = series.accumulate(window, policy=GapPolicy.CARRY_FORWARD)
        return fit_coefficient(entries[0].weight, entries[-1].weight, units)

    def against(self, lot: str, model: GrowthModel, series: ThermalSeries) -> Decimal:
        """How far the lot's latest weight sits from the plan, in percent."""

        entries = self.for_lot(lot)
        window = self.span_for(lot)
        if window is None:
            raise ValidationError("a lot needs two weigh-ins to compare", field="lot")
        units = series.accumulate(window, policy=GapPolicy.CARRY_FORWARD)
        expected = model.grow(entries[0].weight, units)
        return percent_difference(entries[-1].weight.to("g").amount, expected.to("g").amount)

    def is_tracking(
        self,
        lot: str,
        model: GrowthModel,
        series: ThermalSeries,
        *,
        tolerance: Number = 10,
    ) -> bool:
        """Whether the lot is inside a band around the plan."""

        allowed = require_positive(tolerance, field="tolerance")
        return abs(self.against(lot, model, series)) <= allowed

    def has_stalled(self, lot: str, *, days: int = 21, gain: Number = "0.05") -> bool:
        """Whether the lot has failed to put on weight over its last stretch.

        Deliberately not a comparison against the model, because a stall on cold
        water is not a stall. This is the blunt version: the fish are the same
        size they were three weeks ago.
        """

        entries = self.for_lot(lot)
        if len(entries) < 2:
            return False
        last = entries[-1]
        earlier = [entry for entry in entries if (last.day - entry.day).days >= days]
        if not earlier:
            return False
        before = earlier[-1]
        share = to_decimal(gain, field="gain")
        grown = last.weight.to("g").amount / before.weight.to("g").amount - Decimal(1)
        return grown < share


def growth_between(history: GrowthHistory, lot: str, window: DateRange) -> Quantity | None:
    """The weight a lot put on inside a window, or None if it was not weighed."""

    entries = [entry for entry in history.for_lot(lot) if entry.day in window]
    if len(entries) < 2:
        return None
    return entries[-1].weight - entries[0].weight


def refit(history: GrowthHistory, lot: str, series: ThermalSeries) -> GrowthModel:
    """Replace a plan's coefficient with what the lot is actually doing."""

    return history.observed_model(lot, series)
