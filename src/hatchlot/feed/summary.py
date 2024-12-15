"""The feed side of a month, in the four numbers a manager asks for.

What went in, what it converted at, what it cost, and whether the store will
last. The last one is the one that gets forgotten until a Friday, so it is here
rather than left to whoever is doing the ordering.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from ..calendar import DateRange
from ..errors import ValidationError
from ..numeric import Number, require_positive, safe_divide, to_decimal
from ..quantities.base import Quantity
from .conversion import Conversion
from .feeding import FeedingLog, feed_by_lot
from .store import FeedStore


@dataclass(frozen=True, slots=True)
class FeedSummary:
    """One window of feeding across the station."""

    window: DateRange
    fed: Quantity
    lots_fed: int
    on_hand: Quantity
    expiring: tuple[str, ...]
    conversion: Conversion | None
    price_per_kg: Decimal

    @property
    def cost(self) -> Decimal:
        return self.fed.to("kg").amount * self.price_per_kg

    @property
    def daily_mean(self) -> Quantity:
        return Quantity(self.fed.to("kg").amount / Decimal(self.window.days), "kg")

    @property
    def days_left(self) -> int:
        daily = self.daily_mean.to("kg").amount
        if daily <= 0:
            return 0
        return int((self.on_hand.to("kg").amount / daily).to_integral_value(rounding="ROUND_FLOOR"))

    @property
    def ratio(self) -> Decimal | None:
        if self.conversion is None:
            return None
        try:
            return self.conversion.economic_ratio
        except ValidationError:
            return None

    def line(self) -> str:
        ratio = f"{self.ratio:.2f}" if self.ratio is not None else "no gain"
        return (
            f"{self.window}: {self.fed.rounded(0)} fed to {self.lots_fed} lots, "
            f"conversion {ratio}, {self.days_left} days of feed left"
        )


def summarise_feed(
    log: FeedingLog,
    store: FeedStore,
    window: DateRange,
    *,
    conversion: Conversion | None = None,
    price_per_kg: Number = 0,
    expiring_days: int = 60,
) -> FeedSummary:
    """Pull the feed side together for a window."""

    price = to_decimal(price_per_kg, field="price_per_kg")
    if price < 0:
        raise ValidationError("a price cannot be negative", field="price_per_kg")
    totals = feed_by_lot(log, window)
    fed = Quantity(0, "kg")
    for amount in totals.values():
        fed = fed + amount
    return FeedSummary(
        window=window,
        fed=fed,
        lots_fed=len(totals),
        on_hand=store.on_hand(as_of=window.end),
        expiring=tuple(lot.code for lot in store.expiring_within(window.end, expiring_days)),
        conversion=conversion,
        price_per_kg=price,
    )


def reorder_point(summary: FeedSummary, lead_days: int, *, safety_days: int = 7) -> Quantity:
    """The stock level at which an order has to go in.

    Enough to cover the lead time plus a margin, worked off the feeding the
    station has actually been doing rather than a guess.
    """

    if lead_days < 0 or safety_days < 0:
        raise ValidationError("a lead time cannot be negative", field="lead_days")
    daily = summary.daily_mean.to("kg").amount
    return Quantity(daily * Decimal(lead_days + safety_days), "kg")


def needs_ordering(summary: FeedSummary, lead_days: int, *, safety_days: int = 7) -> bool:
    point = reorder_point(summary, lead_days, safety_days=safety_days)
    return summary.on_hand.to("kg").amount <= point.to("kg").amount


def share_of_feed(summary: FeedSummary, log: FeedingLog, lot: str) -> Decimal:
    """How much of a window's feed went to one lot."""

    total = require_positive(summary.fed.to("kg").amount, field="fed")
    return safe_divide(log.fed(lot, summary.window).to("kg").amount, total, field="fed")
