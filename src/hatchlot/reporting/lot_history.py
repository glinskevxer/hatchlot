"""One lot's whole story, from the take to the truck.

This is the report that gets asked for when something has gone wrong, which is
why it is a merge of everything rather than a query against one register. The
ledger says what came and went, the mortality log says what died, the feeding log
says what went in, and the release register says where it ended up. Sorted into
one timeline, those four answer almost every question anybody asks about a lot.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from ..calendar import DateRange
from ..distribution.release import ReleaseRegister
from ..errors import ValidationError
from ..feed.feeding import FeedingLog
from ..identifiers import normalise_code
from ..numeric import safe_divide
from ..quantities.base import Quantity
from ..rearing.ledger import Ledger
from ..rearing.mortality import MortalityLog
from .tables import Align, Column, heading, join_sections, render_pairs, render_table


@dataclass(frozen=True, slots=True, order=True)
class Event:
    """One thing that happened to a lot, whatever register it came from."""

    day: date
    kind: str
    detail: str
    count: Decimal | None = None

    @property
    def line(self) -> str:
        amount = f" {self.count:.0f}" if self.count is not None else ""
        return f"{self.day.isoformat()} {self.kind}{amount} {self.detail}".rstrip()


def timeline(
    lot: str,
    ledger: Ledger,
    mortality: MortalityLog,
    feeding: FeedingLog,
    releases: ReleaseRegister,
    *,
    window: DateRange | None = None,
) -> tuple[Event, ...]:
    """Merge every register's entries for one lot into one ordered list."""

    code = normalise_code(lot, field="lot")
    events: list[Event] = []
    for entry in ledger.for_lot(code):
        events.append(
            Event(
                day=entry.day,
                kind=entry.kind.value,
                detail=entry.reason or entry.counterparty or entry.entered_by,
                count=entry.count,
            )
        )
    for record in mortality.for_lot(code):
        events.append(
            Event(
                day=record.day,
                kind="mortality",
                detail=record.cause.value,
                count=record.count,
            )
        )
    for meal in feeding.for_lot(code):
        events.append(
            Event(
                day=meal.day,
                kind="feeding",
                detail=f"{meal.amount.rounded(2)} of {meal.feed_lot}",
            )
        )
    for release in releases.for_lot(code):
        events.append(
            Event(
                day=release.day,
                kind="release",
                detail=f"{release.water} on {release.request}",
                count=release.fish,
            )
        )
    if window is not None:
        events = [event for event in events if event.day in window]
    return tuple(sorted(events))


@dataclass(frozen=True, slots=True)
class LotHistory:
    """A lot's numbers, gathered from every register that holds any."""

    lot: str
    events: tuple[Event, ...]
    ponded: Decimal
    dead: Decimal
    released: Decimal
    fed: Quantity

    @property
    def span(self) -> DateRange | None:
        if not self.events:
            return None
        return DateRange(self.events[0].day, self.events[-1].day)

    @property
    def survival(self) -> Decimal:
        if self.ponded == 0:
            return Decimal(0)
        return safe_divide(self.ponded - self.dead, self.ponded, field="ponded")

    @property
    def unaccounted(self) -> Decimal:
        """Fish that were neither released nor recorded dead."""

        left = self.ponded - self.dead - self.released
        return left if left > 0 else Decimal(0)


def build_history(
    lot: str,
    ledger: Ledger,
    mortality: MortalityLog,
    feeding: FeedingLog,
    releases: ReleaseRegister,
    *,
    window: DateRange | None = None,
) -> LotHistory:
    """Gather one lot's story."""

    code = normalise_code(lot, field="lot")
    balance = ledger.balance(code)
    return LotHistory(
        lot=code,
        events=timeline(code, ledger, mortality, feeding, releases, window=window),
        ponded=balance.opened + balance.added,
        dead=mortality.total(code, window),
        released=releases.fish_released(code),
        fed=feeding.fed(code, window),
    )


def render_history(history: LotHistory, *, limit: int = 40) -> str:
    """Print a lot history the way it goes in an email."""

    if limit < 1:
        raise ValidationError("a history shows at least one event", field="limit")
    pairs: list[tuple[str, object]] = [
        ("lot", history.lot),
        ("ponded", history.ponded),
        ("dead", history.dead),
        ("released", history.released),
        ("unaccounted", history.unaccounted),
        ("fed", history.fed.rounded(1)),
        ("survival", history.survival.quantize(Decimal("0.0001"))),
    ]
    span = history.span
    if span is not None:
        pairs.insert(1, ("span", str(span)))
    columns = [
        Column(heading="day"),
        Column(heading="event"),
        Column(heading="count", align=Align.RIGHT, places=0),
        Column(heading="detail"),
    ]
    rows = [
        [event.day.isoformat(), event.kind, event.count, event.detail]
        for event in history.events[:limit]
    ]
    sections = [
        heading(f"Lot history {history.lot}"),
        render_pairs(pairs),
        render_table(columns, rows),
    ]
    if len(history.events) > limit:
        sections.append(f"{len(history.events) - limit} more events not shown")
    return join_sections(sections)
