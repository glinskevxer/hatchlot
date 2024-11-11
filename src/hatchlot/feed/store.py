"""The feed store: what is on hand, what came in, and what went out.

Feed is issued first in first out, and not for tidiness. A store that issues the
newest bag first ends up with a pallet of expired feed at the back that somebody
eventually feeds anyway. So the store picks the oldest usable lot for a request
and says which lots it drew from, because a fish health investigation will ask.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from enum import Enum

from ..calendar import DateRange, parse_date
from ..errors import PolicyError, ValidationError
from ..identifiers import normalise_code
from ..journal import JournalLog
from ..numeric import Number, require_positive
from ..quantities.base import Quantity
from ..registry import CodeRegistry
from .feedlot import FeedLot


class StoreEvent(Enum):
    """What happened to the feed."""

    RECEIPT = "receipt"
    ISSUE = "issue"
    DISPOSAL = "disposal"
    ADJUSTMENT = "adjustment"

    @property
    def sign(self) -> int:
        return 1 if self is StoreEvent.RECEIPT else -1


@dataclass(frozen=True, slots=True)
class StoreEntry:
    """One movement of feed in or out of the store."""

    day: date
    feed_lot: str
    event: StoreEvent
    amount: Quantity
    handled_by: str
    destination: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "day", parse_date(self.day))
        object.__setattr__(self, "feed_lot", normalise_code(self.feed_lot, field="feed_lot"))
        if not isinstance(self.event, StoreEvent):
            raise ValidationError(f"{self.event!r} is not a store event", field="event")
        require_positive(self.amount.to("kg").amount, field="amount")
        if not self.handled_by.strip():
            raise ValidationError("a store entry needs whoever made it", field="handled_by")
        object.__setattr__(self, "handled_by", self.handled_by.strip())
        if self.destination:
            object.__setattr__(
                self, "destination", normalise_code(self.destination, field="destination")
            )


@dataclass(frozen=True, slots=True)
class Draw:
    """One lot's share of an issue."""

    feed_lot: str
    amount: Quantity


class FeedStore:
    """Every feed lot on hand, and the record of what moved."""

    def __init__(self) -> None:
        self._lots: CodeRegistry[FeedLot] = CodeRegistry("feed lot", lambda lot: lot.code)
        self._log: JournalLog[StoreEntry] = JournalLog(
            lambda entry: entry.day, lambda entry: entry.feed_lot
        )

    def add(self, lot: FeedLot) -> FeedLot:
        return self._lots.add(lot)

    def get(self, code: str) -> FeedLot:
        return self._lots.get(code)

    def lots(self) -> tuple[FeedLot, ...]:
        return self._lots.all()

    def __len__(self) -> int:
        return len(self._lots)

    def on_hand(self, *, as_of: object | None = None) -> Quantity:
        """Everything usable, which leaves out anything already expired."""

        total = Quantity(0, "kg")
        for lot in self.lots():
            if as_of is not None and lot.is_expired(as_of):
                continue
            total = total + lot.quantity
        return total

    def usable(self, as_of: object, *, pellet_mm: Number | None = None) -> tuple[FeedLot, ...]:
        """Lots that can be fed today, oldest first."""

        candidates = [
            lot
            for lot in self.lots()
            if not lot.is_expired(as_of) and lot.quantity.to("kg").amount > 0
        ]
        if pellet_mm is not None:
            wanted = require_positive(pellet_mm, field="pellet_mm")
            candidates = [lot for lot in candidates if lot.pellet_mm == wanted]
        return tuple(sorted(candidates, key=lambda lot: (lot.made_on, lot.code)))

    def receive(self, lot: FeedLot, day: object, amount: Quantity, handled_by: str) -> StoreEntry:
        """Book feed in against a lot the store already knows."""

        held = self._lots.find(lot.code)
        if held is None:
            self.add(lot)
            held = lot
        else:
            held.receive(amount)
        return self._log.record(
            StoreEntry(
                day=parse_date(day),
                feed_lot=held.code,
                event=StoreEvent.RECEIPT,
                amount=amount,
                handled_by=handled_by,
            )
        )

    def issue(
        self,
        day: object,
        amount: Quantity,
        handled_by: str,
        destination: str,
        *,
        pellet_mm: Number | None = None,
    ) -> tuple[Draw, ...]:
        """Draw feed oldest first, across as many lots as it takes."""

        wanted = require_positive(amount.to("kg").amount, field="amount")
        available = self.usable(day, pellet_mm=pellet_mm)
        total = sum((lot.quantity.to("kg").amount for lot in available), Decimal(0))
        if total < wanted:
            raise PolicyError(f"the store has {total} kg usable, not {wanted}", rule="feed.short")
        draws: list[Draw] = []
        left = wanted
        for lot in available:
            if left <= 0:
                break
            take = min(left, lot.quantity.to("kg").amount)
            lot.draw(Quantity(take, "kg"))
            draws.append(Draw(feed_lot=lot.code, amount=Quantity(take, "kg")))
            self._log.record(
                StoreEntry(
                    day=parse_date(day),
                    feed_lot=lot.code,
                    event=StoreEvent.ISSUE,
                    amount=Quantity(take, "kg"),
                    handled_by=handled_by,
                    destination=destination,
                )
            )
            left -= take
        return tuple(draws)

    def dispose(self, code: str, day: object, handled_by: str, reason: str) -> StoreEntry:
        """Write off what is left of a lot, which expiry usually forces."""

        if not reason.strip():
            raise ValidationError("a disposal needs a reason", field="reason")
        lot = self.get(code)
        remaining = lot.quantity
        if remaining.to("kg").amount <= 0:
            raise ValidationError(f"feed lot {lot.code} is already empty", field="feed_lot")
        lot.draw(remaining)
        return self._log.record(
            StoreEntry(
                day=parse_date(day),
                feed_lot=lot.code,
                event=StoreEvent.DISPOSAL,
                amount=remaining,
                handled_by=handled_by,
                destination=reason.strip().replace(" ", "-")[:24],
            )
        )

    def expiring_within(self, as_of: object, days: int) -> tuple[FeedLot, ...]:
        """Lots that go out of date inside a window, so they get used first."""

        if days < 0:
            raise ValidationError("that is not a window", field="days")
        when = parse_date(as_of)
        horizon = when + timedelta(days=days)
        return tuple(
            lot
            for lot in self.lots()
            if lot.quantity.to("kg").amount > 0 and when <= lot.expires_on <= horizon
        )

    def issued_to(self, destination: str, window: DateRange | None = None) -> Quantity:
        """How much feed went to one place."""

        code = normalise_code(destination, field="destination")
        entries = self._log.within(window) if window is not None else self._log.all()
        total = Quantity(0, "kg")
        for entry in entries:
            if entry.event is StoreEvent.ISSUE and entry.destination == code:
                total = total + entry.amount
        return total

    def movements(self, feed_lot: str) -> tuple[StoreEntry, ...]:
        return self._log._for_key(feed_lot)
