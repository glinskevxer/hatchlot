"""What was actually fed, which is never quite what the plan said.

The plan is a number off a chart. The feeding record is what a person with a
scoop did, and the gap between them is worth watching in both directions. Under
the plan for a week is a lot that is off its feed, which is the earliest sign of
almost everything. Over the plan is feed going through the raceway and out the
drain, which shows up later in the effluent report and in the bill.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from enum import Enum

from ..calendar import DateRange, parse_date
from ..errors import ValidationError
from ..identifiers import normalise_code
from ..journal import JournalLog
from ..numeric import Number, percent_difference, require_positive, safe_divide, to_decimal
from ..quantities.base import Quantity


class FeedMethod(Enum):
    """How the feed was put in the water."""

    HAND = "hand"
    BELT = "belt"
    DEMAND = "demand"
    AUTOMATIC = "automatic"

    @property
    def is_measured(self) -> bool:
        """A demand feeder is emptied rather than weighed, so its number is soft."""

        return self is not FeedMethod.DEMAND


@dataclass(frozen=True, slots=True, order=True)
class Feeding:
    """One feeding of one lot."""

    day: date
    lot: str
    amount: Quantity
    method: FeedMethod
    feed_lot: str
    fed_by: str

    def __init__(
        self,
        day: object,
        lot: str,
        amount: Quantity,
        method: FeedMethod,
        feed_lot: str,
        fed_by: str,
    ) -> None:
        object.__setattr__(self, "day", parse_date(day))
        object.__setattr__(self, "lot", normalise_code(lot, field="lot"))
        require_positive(amount.to("kg").amount, field="amount")
        object.__setattr__(self, "amount", amount)
        if not isinstance(method, FeedMethod):
            raise ValidationError(f"{method!r} is not a feed method", field="method")
        object.__setattr__(self, "method", method)
        object.__setattr__(self, "feed_lot", normalise_code(feed_lot, field="feed_lot"))
        if not fed_by.strip():
            raise ValidationError("a feeding needs whoever did it", field="fed_by")
        object.__setattr__(self, "fed_by", fed_by.strip())


class FeedingLog(JournalLog[Feeding]):
    """Every feeding, over every lot."""

    def __init__(self) -> None:
        super().__init__(lambda entry: entry.day, lambda entry: entry.lot)

    def for_lot(self, lot: str) -> tuple[Feeding, ...]:
        return self._for_key(lot)

    def fed(self, lot: str, window: DateRange | None = None) -> Quantity:
        entries = self.for_lot(lot)
        if window is not None:
            entries = tuple(entry for entry in entries if entry.day in window)
        total = Quantity(0, "kg")
        for entry in entries:
            total = total + entry.amount
        return total

    def fed_on(self, lot: str, day: object) -> Quantity:
        when = parse_date(day)
        total = Quantity(0, "kg")
        for entry in self.for_lot(lot):
            if entry.day == when:
                total = total + entry.amount
        return total

    def feed_lots_used(self, lot: str, window: DateRange | None = None) -> tuple[str, ...]:
        """Which feed lots went into a fish lot, which is the traceback question."""

        entries = self.for_lot(lot)
        if window is not None:
            entries = tuple(entry for entry in entries if entry.day in window)
        return tuple(sorted({entry.feed_lot for entry in entries}))

    def days_fed(self, lot: str, window: DateRange) -> int:
        return len({entry.day for entry in self.for_lot(lot) if entry.day in window})

    def against_plan(self, lot: str, day: object, planned: Quantity) -> Decimal:
        """How far a day's feeding sat from the plan, in percent."""

        wanted = require_positive(planned.to("kg").amount, field="planned")
        return percent_difference(self.fed_on(lot, day).to("kg").amount, wanted)

    def is_off_feed(
        self, lot: str, window: DateRange, planned_daily: Quantity, *, share: Number = "0.7"
    ) -> bool:
        """Whether a lot has been eating less than it should over a stretch."""

        floor = to_decimal(share, field="share")
        if not 0 < floor <= 1:
            raise ValidationError("that is not a share of the plan", field="share")
        expected = require_positive(planned_daily.to("kg").amount, field="planned_daily") * Decimal(
            window.days
        )
        return self.fed(lot, window).to("kg").amount < expected * floor

    def hand_fed_share(self, lot: str) -> Decimal:
        """How much of a lot's feed went in by a method that was weighed."""

        entries = self.for_lot(lot)
        total = sum((entry.amount.to("kg").amount for entry in entries), Decimal(0))
        if total == 0:
            return Decimal(0)
        measured = sum(
            (entry.amount.to("kg").amount for entry in entries if entry.method.is_measured),
            Decimal(0),
        )
        return measured / total


def feed_by_lot(log: FeedingLog, window: DateRange) -> dict[str, Quantity]:
    """Everything fed inside a window, split by fish lot."""

    totals: dict[str, Quantity] = {}
    for entry in log.within(window):
        running = totals.get(entry.lot, Quantity(0, "kg"))
        totals[entry.lot] = running + entry.amount
    return totals


def feed_cost(fed: Quantity, price_per_kg: Number) -> Decimal:
    """What a quantity of feed cost, in whatever currency the price is in."""

    price = to_decimal(price_per_kg, field="price_per_kg")
    if price < 0:
        raise ValidationError("a price cannot be negative", field="price_per_kg")
    return fed.to("kg").amount * price


def feed_per_fish(fed: Quantity, population: Number) -> Quantity:
    """The feed one fish got, which is how a nursery compares two troughs."""

    count = require_positive(population, field="population")
    return Quantity(safe_divide(fed.to("g").amount, count, field="population"), "g")
