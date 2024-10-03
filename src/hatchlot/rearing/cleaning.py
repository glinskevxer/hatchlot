"""Cleaning the units, and the solids that come off when you do.

Waste settles at the bottom of a raceway and stays there until somebody brushes
it into the drain. How often that has to happen is not a fixed interval: it
follows the feed, because the feed is where the solids come from. A raceway
carrying twice the biomass fouls in half the time.

The solids number matters twice over. It sets the cleaning interval, and it is
the same number the discharge permit is written against, so it is worked out
once here and used in both places.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from enum import Enum

from ..calendar import DateRange, parse_date
from ..errors import ValidationError
from ..identifiers import normalise_code
from ..journal import Journal
from ..numeric import Number, require_non_negative, require_positive, to_decimal
from ..quantities.base import Quantity
from .container import Container, ContainerKind

# A pound of dry feed leaves roughly this much settleable solids behind, after
# what the fish digest and what dissolves. It is the figure the station's own
# discharge monitoring is calibrated against.
SOLIDS_PER_FEED = Decimal("0.25")


class CleaningMethod(Enum):
    """How the unit was cleaned, which decides what it took out."""

    BRUSH = "brush"
    VACUUM = "vacuum"
    FLUSH = "flush"
    DRAIN = "drain"

    @property
    def removes_solids(self) -> bool:
        """A flush pushes solids downstream rather than taking them out."""

        return self is not CleaningMethod.FLUSH


@dataclass(frozen=True, slots=True, order=True)
class Cleaning:
    """One cleaning of one unit."""

    day: date
    container: str
    method: CleaningMethod
    cleaned_by: str
    solids: Quantity | None = None

    def __init__(
        self,
        day: object,
        container: str,
        method: CleaningMethod,
        cleaned_by: str,
        solids: Quantity | None = None,
    ) -> None:
        object.__setattr__(self, "day", parse_date(day))
        object.__setattr__(self, "container", normalise_code(container, field="container"))
        if not isinstance(method, CleaningMethod):
            raise ValidationError(f"{method!r} is not a cleaning method", field="method")
        object.__setattr__(self, "method", method)
        if not cleaned_by.strip():
            raise ValidationError("a cleaning needs whoever did it", field="cleaned_by")
        object.__setattr__(self, "cleaned_by", cleaned_by.strip())
        if solids is not None:
            require_non_negative(solids.to("kg").amount, field="solids")
        object.__setattr__(self, "solids", solids)


def solids_from_feed(feed: Quantity, *, share: Number = SOLIDS_PER_FEED) -> Quantity:
    """The settleable solids a quantity of feed leaves behind."""

    fed = require_non_negative(feed.to("kg").amount, field="feed")
    fraction = require_non_negative(share, field="share")
    if fraction > 1:
        raise ValidationError("a solids share over one is not a share", field="share")
    return Quantity(fed * fraction, "kg")


def cleaning_interval(container: Container, biomass: Quantity, *, base_days: int = 14) -> int:
    """How many days a unit can go between cleanings at a loading.

    Falls with the biomass it is carrying, and a self cleaning unit gets longer
    because its own current does part of the job.
    """

    if base_days < 1:
        raise ValidationError("an interval has at least a day in it", field="base_days")
    volume = require_positive(container.volume.to("m3").amount, field="volume")
    density = biomass.to("kg").amount / volume
    if density <= 0:
        return base_days
    scale = Decimal(2) if container.kind.is_self_cleaning else Decimal(1)
    days = Decimal(base_days) * scale / (Decimal(1) + density / Decimal(10))
    whole = int(days.to_integral_value(rounding="ROUND_FLOOR"))
    return max(whole, 1)


class CleaningLog:
    """Every cleaning on the station."""

    def __init__(self, cleanings: Iterable[Cleaning] = ()) -> None:
        self._journal: Journal[Cleaning] = Journal(
            day_of=lambda entry: entry.day, key_of=lambda entry: entry.container
        )
        self._journal.extend(cleanings)

    def record(self, entry: Cleaning) -> Cleaning:
        return self._journal.record(entry)

    def __len__(self) -> int:
        return len(self._journal)

    def for_container(self, container: str) -> tuple[Cleaning, ...]:
        return self._journal.for_key(container)

    def within(self, window: DateRange) -> tuple[Cleaning, ...]:
        return self._journal.within(window)

    def last_cleaned(self, container: str) -> date | None:
        entries = self.for_container(container)
        return entries[-1].day if entries else None

    def solids_removed(self, window: DateRange | None = None) -> Quantity:
        """Everything actually taken out, which a flush does not count toward."""

        entries = self.within(window) if window is not None else self._journal.all()
        total = Quantity(0, "kg")
        for entry in entries:
            if entry.solids is not None and entry.method.removes_solids:
                total = total + entry.solids
        return total

    def due_on(
        self, container: Container, biomass: Quantity, *, base_days: int = 14
    ) -> date | None:
        """When a unit next falls due, or None if it has never been cleaned."""

        last = self.last_cleaned(container.code)
        if last is None:
            return None
        return last + timedelta(days=cleaning_interval(container, biomass, base_days=base_days))

    def is_overdue(
        self,
        container: Container,
        biomass: Quantity,
        as_of: object,
        *,
        base_days: int = 14,
    ) -> bool:
        """A unit never cleaned is overdue, which is the answer that gets it done."""

        due = self.due_on(container, biomass, base_days=base_days)
        if due is None:
            return True
        return parse_date(as_of) > due


def expected_solids(feed_by_container: dict[str, Quantity]) -> Quantity:
    """The solids a station should have taken out, off what it fed."""

    total = Quantity(0, "kg")
    for feed in feed_by_container.values():
        total = total + solids_from_feed(feed)
    return total


def capture_share(removed: Quantity, expected: Quantity) -> Decimal:
    """The share of the expected solids the cleaning record accounts for."""

    produced = to_decimal(expected.to("kg").amount, field="expected")
    if produced <= 0:
        raise ValidationError("no solids were expected", field="expected")
    return removed.to("kg").amount / produced


def kind_interval(kind: ContainerKind, *, base_days: int = 14) -> int:
    """The interval a unit of this kind gets with nothing in it."""

    if base_days < 1:
        raise ValidationError("an interval has at least a day in it", field="base_days")
    return base_days * 2 if kind.is_self_cleaning else base_days
