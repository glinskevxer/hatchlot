"""Matching the fish that exist against the requests that were made.

Every spring there are more fish asked for than there are, and the fish that
exist are the wrong size for half the requests anyway. So the allocation is two
steps and they are separate on purpose: first work out which lots a request would
even accept, then divide what is left among the ones that qualify.

Three policies divide it, and unlike a lot of software choices these really are
different answers. Strict priority fills the top of the list and leaves the
bottom empty. Pro rata gives everybody most of what they asked for and nobody
what they need. Best fit puts the closest size in each water and gets the fish
into the right places at the cost of the priority order.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from enum import Enum

from ..calendar import parse_date
from ..errors import ValidationError
from ..identifiers import normalise_code
from ..numeric import Number, require_positive, safe_divide
from ..quantities.base import Quantity
from ..species import resolve_species
from .request import StockingRequest


class AllocationPolicy(Enum):
    """How the fish that exist are divided among the requests."""

    PRIORITY = "priority"
    PRO_RATA = "pro_rata"
    BEST_FIT = "best_fit"


@dataclass(frozen=True, slots=True)
class Offer:
    """One lot the station could send out."""

    lot: str
    species: str
    fish: Decimal
    mean_weight: Quantity
    ready_on: date

    def __init__(
        self, lot: str, species: str, fish: Number, mean_weight: Quantity, ready_on: object
    ) -> None:
        object.__setattr__(self, "lot", normalise_code(lot, field="lot"))
        object.__setattr__(self, "species", resolve_species(species).code)
        object.__setattr__(self, "fish", require_positive(fish, field="fish"))
        require_positive(mean_weight.to("g").amount, field="mean_weight")
        object.__setattr__(self, "mean_weight", mean_weight)
        object.__setattr__(self, "ready_on", parse_date(ready_on))


@dataclass(frozen=True, slots=True)
class Assignment:
    """One lot sent against one request."""

    request: str
    lot: str
    fish: Decimal
    size_gap: Decimal

    @property
    def is_exact_size(self) -> bool:
        return self.size_gap == 0


@dataclass(frozen=True, slots=True)
class AllocationPlan:
    """The whole allocation, and what it left over."""

    policy: AllocationPolicy
    assignments: tuple[Assignment, ...]
    unfilled: tuple[str, ...]
    unused: dict[str, Decimal]

    @property
    def fish_allocated(self) -> Decimal:
        return sum((entry.fish for entry in self.assignments), Decimal(0))

    def for_request(self, code: str) -> tuple[Assignment, ...]:
        key = normalise_code(code, field="request")
        return tuple(entry for entry in self.assignments if entry.request == key)

    def for_lot(self, code: str) -> tuple[Assignment, ...]:
        key = normalise_code(code, field="lot")
        return tuple(entry for entry in self.assignments if entry.lot == key)

    def line(self) -> str:
        return (
            f"{self.policy.value}: {self.fish_allocated:.0f} fish over "
            f"{len(self.assignments)} assignments, {len(self.unfilled)} requests unfilled"
        )


def suits(request: StockingRequest, offer: Offer) -> bool:
    """Whether a request would take this lot at all."""

    if request.species != offer.species:
        return False
    if not request.accepts_size(offer.mean_weight):
        return False
    return offer.ready_on <= request.window.end


def size_gap(request: StockingRequest, offer: Offer) -> Decimal:
    """How far off the requested size a lot is, as a share of the target."""

    wanted = request.target_weight.to("g").amount
    return abs(offer.mean_weight.to("g").amount - wanted) / wanted


def allocate(
    requests: list[StockingRequest],
    offers: list[Offer],
    policy: AllocationPolicy = AllocationPolicy.PRIORITY,
) -> AllocationPlan:
    """Divide the fish that exist among the requests that would take them."""

    if not requests:
        raise ValidationError("nothing was asked for", field="requests")
    if not isinstance(policy, AllocationPolicy):
        raise ValidationError(f"{policy!r} is not an allocation policy", field="policy")
    remaining = {offer.lot: offer.fish for offer in offers}
    by_lot = {offer.lot: offer for offer in offers}
    if len(by_lot) != len(offers):
        raise ValidationError("the same lot is offered twice", field="offers")
    open_requests = [request for request in requests if not request.state.is_closed]
    ordered = sorted(
        open_requests,
        key=lambda request: (request.priority, request.window.start, request.code),
    )
    assignments: list[Assignment] = []
    wanted = {request.code: request.outstanding for request in ordered}
    if policy is AllocationPolicy.PRO_RATA:
        for request in ordered:
            usable = sum(
                (remaining[offer.lot] for offer in offers if suits(request, offer)),
                Decimal(0),
            )
            asked = sum(
                (
                    other.outstanding
                    for other in ordered
                    if any(suits(other, offer) for offer in offers)
                ),
                Decimal(0),
            )
            if asked > 0 and usable > 0:
                share = min(Decimal(1), usable / asked)
                wanted[request.code] = request.outstanding * share
    for request in ordered:
        need = wanted[request.code]
        if need <= 0:
            continue
        candidates = [
            offer for offer in offers if suits(request, offer) and remaining[offer.lot] > 0
        ]
        if policy is AllocationPolicy.BEST_FIT:
            candidates.sort(key=lambda offer: (size_gap(request, offer), offer.lot))
        else:
            candidates.sort(key=lambda offer: (offer.ready_on, offer.lot))
        for offer in candidates:
            if need <= 0:
                break
            take = min(need, remaining[offer.lot])
            if take <= 0:
                continue
            assignments.append(
                Assignment(
                    request=request.code,
                    lot=offer.lot,
                    fish=take,
                    size_gap=size_gap(request, offer),
                )
            )
            remaining[offer.lot] -= take
            need -= take
    filled = {entry.request for entry in assignments}
    return AllocationPlan(
        policy=policy,
        assignments=tuple(assignments),
        unfilled=tuple(sorted(request.code for request in ordered if request.code not in filled)),
        unused={lot: left for lot, left in remaining.items() if left > 0},
    )


def coverage(plan: AllocationPlan, requests: list[StockingRequest]) -> Decimal:
    """The share of what was asked for that the plan covers."""

    asked = sum(
        (request.outstanding for request in requests if not request.state.is_closed),
        Decimal(0),
    )
    if asked == 0:
        raise ValidationError("nothing was outstanding", field="requests")
    return safe_divide(plan.fish_allocated, asked, field="requests")


def mean_size_gap(plan: AllocationPlan) -> Decimal:
    """How far off the requested sizes the plan is, weighted by fish."""

    if not plan.assignments:
        return Decimal(0)
    total = plan.fish_allocated
    if total == 0:
        return Decimal(0)
    weighted = sum((entry.fish * entry.size_gap for entry in plan.assignments), Decimal(0))
    return weighted / total
