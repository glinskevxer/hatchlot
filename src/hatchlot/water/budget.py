"""Handing out the water when there is not enough of it.

In a dry August the springs come up short and somebody has to decide which
raceways get their full flow. Three policies cover what stations actually do,
and they are genuinely different answers rather than three spellings of one: a
strict priority order starves the bottom of the list, a flat pro rata cut leaves
every unit slightly short, and serving the minimums first protects the fish at
the cost of nobody getting what they asked for.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum

from ..errors import ValidationError
from ..identifiers import normalise_code
from ..numeric import require_non_negative
from ..quantities.base import Quantity

FLOW_UNIT = "gpm"


class AllocationPolicy(Enum):
    """How a short supply is divided."""

    PRIORITY_FIRST = "priority_first"
    PRO_RATA = "pro_rata"
    MINIMUM_FIRST = "minimum_first"


@dataclass(frozen=True, slots=True)
class Demand:
    """One unit's ask: what it wants, what it cannot go below, and how it ranks."""

    container: str
    requested: Quantity
    minimum: Quantity
    priority: int = 5

    def __post_init__(self) -> None:
        object.__setattr__(self, "container", normalise_code(self.container, field="container"))
        require_non_negative(self.requested.amount, field="requested")
        require_non_negative(self.minimum.amount, field="minimum")
        if self.minimum > self.requested:
            raise ValidationError("a unit cannot need more than it asked for", field="minimum")
        if not 1 <= self.priority <= 9:
            raise ValidationError("priority runs from 1 to 9", field="priority")


@dataclass(frozen=True, slots=True)
class Grant:
    """What one unit ended up with."""

    container: str
    granted: Quantity
    requested: Quantity
    minimum: Quantity

    @property
    def shortfall(self) -> Quantity:
        return self.requested.to(FLOW_UNIT) - self.granted.to(FLOW_UNIT)

    @property
    def is_satisfied(self) -> bool:
        return self.granted.to(FLOW_UNIT) >= self.requested.to(FLOW_UNIT)

    @property
    def is_below_minimum(self) -> bool:
        return self.granted.to(FLOW_UNIT) < self.minimum.to(FLOW_UNIT)


@dataclass(frozen=True, slots=True)
class Plan:
    """The whole allocation, and what it cost."""

    policy: AllocationPolicy
    supply: Quantity
    grants: tuple[Grant, ...]

    @property
    def granted_total(self) -> Quantity:
        total = Quantity(0, FLOW_UNIT)
        for grant in self.grants:
            total = total + grant.granted
        return total

    @property
    def unallocated(self) -> Quantity:
        return self.supply.to(FLOW_UNIT) - self.granted_total

    @property
    def starved(self) -> tuple[Grant, ...]:
        """Every unit that came out below the flow it said it could not go under."""

        return tuple(grant for grant in self.grants if grant.is_below_minimum)

    def for_container(self, container: str) -> Grant:
        code = normalise_code(container, field="container")
        for grant in self.grants:
            if grant.container == code:
                return grant
        raise ValidationError(f"{code} is not in this plan", field="container")


def allocate(
    supply: Quantity,
    demands: list[Demand],
    policy: AllocationPolicy = AllocationPolicy.MINIMUM_FIRST,
) -> Plan:
    """Divide a supply across the units that asked for it."""

    if not demands:
        raise ValidationError("nothing asked for water", field="demands")
    codes = [demand.container for demand in demands]
    if len(set(codes)) != len(codes):
        raise ValidationError("a unit cannot ask twice in one plan", field="demands")
    available = require_non_negative(supply.to(FLOW_UNIT).amount, field="supply")
    if policy is AllocationPolicy.PRIORITY_FIRST:
        granted = _priority_first(available, demands)
    elif policy is AllocationPolicy.PRO_RATA:
        granted = _pro_rata(available, demands)
    else:
        granted = _minimum_first(available, demands)
    grants = tuple(
        Grant(
            container=demand.container,
            granted=Quantity(granted[demand.container], FLOW_UNIT),
            requested=demand.requested.to(FLOW_UNIT),
            minimum=demand.minimum.to(FLOW_UNIT),
        )
        for demand in demands
    )
    return Plan(policy=policy, supply=supply.to(FLOW_UNIT), grants=grants)


def _ordered(demands: list[Demand]) -> list[Demand]:
    return sorted(demands, key=lambda demand: (demand.priority, demand.container))


def _priority_first(available: Decimal, demands: list[Demand]) -> dict[str, Decimal]:
    left = available
    granted: dict[str, Decimal] = {}
    for demand in _ordered(demands):
        want = demand.requested.to(FLOW_UNIT).amount
        take = min(want, left)
        granted[demand.container] = take
        left -= take
    return granted


def _pro_rata(available: Decimal, demands: list[Demand]) -> dict[str, Decimal]:
    wanted = sum((demand.requested.to(FLOW_UNIT).amount for demand in demands), Decimal(0))
    if wanted == 0:
        return {demand.container: Decimal(0) for demand in demands}
    share = min(Decimal(1), available / wanted)
    return {demand.container: demand.requested.to(FLOW_UNIT).amount * share for demand in demands}


def _minimum_first(available: Decimal, demands: list[Demand]) -> dict[str, Decimal]:
    granted: dict[str, Decimal] = {}
    left = available
    for demand in _ordered(demands):
        floor = demand.minimum.to(FLOW_UNIT).amount
        take = min(floor, left)
        granted[demand.container] = take
        left -= take
    if left <= 0:
        return granted
    remaining = sum(
        (demand.requested.to(FLOW_UNIT).amount - granted[demand.container] for demand in demands),
        Decimal(0),
    )
    if remaining <= 0:
        return granted
    share = min(Decimal(1), left / remaining)
    for demand in demands:
        headroom = demand.requested.to(FLOW_UNIT).amount - granted[demand.container]
        granted[demand.container] += headroom * share
    return granted
