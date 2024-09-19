"""What a unit is actually carrying, against what it is allowed to carry.

The capacity maths lives in the water package because it is a property of the
water. This is the join: a lot, sitting in a container, on a water, at a
temperature, and the answer to whether that is all right.

The answer has three levels rather than two. A unit over its limit is a refusal.
A unit inside the station's tolerance of its limit is a warning, because the
fish grow every day and next week it will be over. Anything else is fine.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum

from ..errors import PolicyError
from ..numeric import Number, require_non_negative, safe_divide
from ..quantities.base import Quantity
from ..quantities.temperature import Temperature
from ..station import DEFAULT_PROFILE, StationProfile
from ..water.capacity import BindingLimit, Capacity, carrying_capacity
from .container import Container
from .lot import RearingLot


class LoadingStatus(Enum):
    """How a unit is sitting against its limit, worst last."""

    OK = "ok"
    WARNING = "warning"
    OVER = "over"

    @property
    def is_actionable(self) -> bool:
        return self is not LoadingStatus.OK


@dataclass(frozen=True, slots=True)
class Loading:
    """One unit, one lot, and the three limits worked out."""

    container: str
    lot: str
    biomass: Quantity
    capacity: Capacity
    status: LoadingStatus

    @property
    def binding(self) -> BindingLimit:
        return self.capacity.binding

    @property
    def allowed(self) -> Quantity:
        return self.capacity.allowed

    @property
    def headroom(self) -> Quantity:
        return self.capacity.headroom(self.biomass)

    @property
    def used_share(self) -> Decimal:
        return safe_divide(
            self.biomass.to("lb").amount, self.allowed.to("lb").amount, field="allowed"
        )

    def line(self) -> str:
        return (
            f"{self.container}/{self.lot}: {self.used_share:.0%} of the "
            f"{self.binding.value} limit, {self.status.value}"
        )


def assess(
    container: Container,
    lot: RearingLot,
    *,
    inflow_mgL: Number = "10.0",
    floor_mgL: Number = "6.0",
    temperature: Temperature | None = None,
    profile: StationProfile | None = None,
) -> Loading:
    """Work out what a unit is carrying against what the water allows.

    The species limits come off the lot rather than being passed in, because a
    raceway of steelhead and a raceway of chum are not allowed the same loading
    and a call site that has to remember that will one day forget.
    """

    station = profile or DEFAULT_PROFILE
    water = temperature or Temperature(10, "C")
    species = lot.species
    capacity = carrying_capacity(
        flow=container.flow,
        volume=container.volume,
        length=lot.length,
        inflow_mgL=inflow_mgL,
        floor_mgL=floor_mgL,
        temperature=water,
        fish_weight_g=lot.mean_weight.to("g").amount,
        flow_index=species.flow_index_limit,
        density_index=species.density_index_limit,
    )
    biomass = lot.biomass
    tolerance = require_non_negative(station.loading_tolerance, field="loading_tolerance")
    allowed = capacity.allowed.to("lb").amount
    carrying = biomass.to("lb").amount
    if carrying > allowed:
        status = LoadingStatus.OVER
    elif allowed > 0 and carrying >= allowed * (Decimal(1) - tolerance):
        status = LoadingStatus.WARNING
    else:
        status = LoadingStatus.OK
    return Loading(
        container=container.code,
        lot=str(lot.code),
        biomass=biomass,
        capacity=capacity,
        status=status,
    )


def check_loading(loading: Loading) -> None:
    """Refuse a unit that is over, naming the limit that bound."""

    if loading.status is LoadingStatus.OVER:
        raise PolicyError(
            f"{loading.container} is carrying {loading.biomass.rounded(0)} against a "
            f"{loading.binding.value} limit of {loading.allowed.rounded(0)}",
            rule=f"loading.{loading.binding.value}",
        )


def room_for(loading: Loading, mean_weight: Quantity) -> Decimal:
    """How many more fish of a size a unit could take before it is full."""

    headroom = loading.headroom.to("g").amount
    if headroom <= 0:
        return Decimal(0)
    each = mean_weight.to("g").amount
    return safe_divide(headroom, each, field="mean_weight")


def days_until_full(
    loading: Loading, daily_growth_share: Number, *, limit_days: int = 365
) -> int | None:
    """How long a unit has before growth puts it over.

    None means it is either over already or growing too slowly to matter inside
    the horizon, and those are deliberately the same answer: neither one is a
    date to put in a plan.
    """

    growth = require_non_negative(daily_growth_share, field="daily_growth_share")
    if growth == 0 or loading.status is LoadingStatus.OVER:
        return None
    carrying = loading.biomass.to("lb").amount
    allowed = loading.allowed.to("lb").amount
    days = 0
    while days < limit_days:
        days += 1
        carrying *= Decimal(1) + growth
        if carrying > allowed:
            return days
    return None
