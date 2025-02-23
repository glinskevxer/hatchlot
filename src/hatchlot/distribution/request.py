"""Stocking requests, which are what the hatchery is actually for.

Somebody who manages a water asks for fish: a species, a size, a number, and a
window of days when the water is fit to take them. The hatchery cannot meet all
of them and has to be able to say why not, which means the request has to carry
enough to be judged: what it will accept as well as what it wants.

A request that will take anything is a request that always gets filled last, so
the tolerance on size and date is part of the record rather than something
negotiated on the phone in May.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum

from ..calendar import DateRange, parse_date
from ..errors import ValidationError
from ..identifiers import normalise_code, normalise_species
from ..numeric import Number, require_positive, safe_divide, to_decimal
from ..quantities.base import Quantity
from ..registry import CodeRegistry
from ..species import resolve_species


class RequestState(Enum):
    """Where a request is."""

    OPEN = "open"
    PARTIAL = "partial"
    FILLED = "filled"
    DECLINED = "declined"
    LAPSED = "lapsed"

    @property
    def is_closed(self) -> bool:
        return self in {RequestState.FILLED, RequestState.DECLINED, RequestState.LAPSED}


@dataclass
class StockingRequest:
    """One water's ask for one species and size."""

    code: str
    water: str
    species: str
    fish: Decimal
    target_weight: Quantity
    window: DateRange
    requested_by: str
    priority: int = 5
    size_tolerance: Decimal = Decimal("0.25")
    delivered: Decimal = Decimal(0)
    state: RequestState = RequestState.OPEN
    note: str = ""

    def __post_init__(self) -> None:
        self.code = normalise_code(self.code, field="request")
        self.water = normalise_code(self.water, field="water")
        self.species = normalise_species(self.species)
        self.fish = require_positive(self.fish, field="fish")
        require_positive(self.target_weight.to("g").amount, field="target_weight")
        if not self.requested_by.strip():
            raise ValidationError("a request needs whoever made it", field="requested_by")
        self.requested_by = self.requested_by.strip()
        if not 1 <= self.priority <= 9:
            raise ValidationError("priority runs from 1 to 9", field="priority")
        if not 0 <= self.size_tolerance <= 1:
            raise ValidationError("a size tolerance is a share", field="size_tolerance")

    @property
    def outstanding(self) -> Decimal:
        left = self.fish - self.delivered
        return left if left > 0 else Decimal(0)

    @property
    def filled_share(self) -> Decimal:
        return safe_divide(self.delivered, self.fish, field="fish")

    def accepts_size(self, weight: Quantity) -> bool:
        """Whether a fish of this size is inside what the request will take."""

        wanted = self.target_weight.to("g").amount
        offered = weight.to("g").amount
        if offered <= 0:
            raise ValidationError("a fish has a weight", field="weight")
        return abs(offered - wanted) / wanted <= self.size_tolerance

    def accepts_day(self, day: object) -> bool:
        return parse_date(day) in self.window

    def deliver(self, fish: Number, day: object) -> Decimal:
        """Book a delivery against the request."""

        if self.state.is_closed:
            raise ValidationError(f"request {self.code} is {self.state.value}", field="state")
        count = require_positive(fish, field="fish")
        if count > self.outstanding:
            raise ValidationError(
                f"{count} fish is more than the {self.outstanding} outstanding", field="fish"
            )
        if not self.accepts_day(day):
            raise ValidationError(f"{parse_date(day)} is outside {self.window}", field="day")
        self.delivered += count
        self.state = RequestState.FILLED if self.outstanding == 0 else RequestState.PARTIAL
        return self.outstanding

    def decline(self, reason: str) -> None:
        if not reason.strip():
            raise ValidationError("declining a request needs a reason", field="reason")
        if self.state.is_closed:
            raise ValidationError(f"request {self.code} is {self.state.value}", field="state")
        self.state = RequestState.DECLINED
        self.note = reason.strip()

    def lapse(self, as_of: object) -> bool:
        """Close a request whose window has gone by, which most of them do."""

        if self.state.is_closed:
            return False
        if parse_date(as_of) <= self.window.end:
            return False
        self.state = RequestState.LAPSED
        return True

    def biomass(self) -> Quantity:
        """What the whole request weighs at its target size."""

        return Quantity(self.fish * self.target_weight.to("kg").amount, "kg")


class RequestBook(CodeRegistry[StockingRequest]):
    """Every stocking request the station is holding."""

    def __init__(self) -> None:
        super().__init__("request", lambda request: request.code)

    def open_requests(self) -> tuple[StockingRequest, ...]:
        return self.where(lambda request: not request.state.is_closed)

    def for_species(self, species: str) -> tuple[StockingRequest, ...]:
        code = resolve_species(species).code
        return self.where(lambda request: request.species == code)

    def for_water(self, water: str) -> tuple[StockingRequest, ...]:
        code = normalise_code(water, field="water")
        return self.where(lambda request: request.water == code)

    def due_within(self, window: DateRange) -> tuple[StockingRequest, ...]:
        return self.where(
            lambda request: not request.state.is_closed and request.window.overlaps(window)
        )

    def outstanding_fish(self, species: str | None = None) -> Decimal:
        requests = self.for_species(species) if species else self.all()
        return sum(
            (request.outstanding for request in requests if not request.state.is_closed),
            Decimal(0),
        )

    def lapse_all(self, as_of: object) -> tuple[str, ...]:
        """Close everything whose window has passed, and say what closed."""

        closed = [request.code for request in self.all() if request.lapse(as_of)]
        return tuple(closed)

    def by_priority(self) -> tuple[StockingRequest, ...]:
        return tuple(
            sorted(
                self.open_requests(),
                key=lambda request: (request.priority, request.window.start, request.code),
            )
        )


def total_biomass(requests: list[StockingRequest]) -> Quantity:
    total = Quantity(0, "kg")
    for request in requests:
        total = total + request.biomass()
    return total


def fill_rate(requests: list[StockingRequest]) -> Decimal:
    """The share of everything asked for that was actually delivered."""

    asked = sum((request.fish for request in requests), Decimal(0))
    if asked == 0:
        raise ValidationError("nothing was asked for", field="requests")
    given = sum((request.delivered for request in requests), Decimal(0))
    return to_decimal(given, field="delivered") / asked
