"""Discharge limits, and the net that the word net is doing in them.

A hatchery permit is written on what the station adds to the water, not on what
comes out of the pipe. The creek arrives with solids in it already, so the number
that matters is the outfall reading minus the intake reading, and a permit
written on gross values is a different and much harder permit.

The other half is that limits are not all concentrations. Some are mass per day,
which moves with the flow, and some are tied to how much feed was fed, which
moves with the fish. A station can pass the concentration limit and fail the mass
limit on the same sample by opening a valve.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum

from ..errors import ValidationError
from ..numeric import require_non_negative, require_positive, safe_divide, to_decimal
from ..quantities.base import Quantity


class Parameter(Enum):
    """What the permit puts a number on."""

    SETTLEABLE_SOLIDS = "settleable_solids"
    SUSPENDED_SOLIDS = "suspended_solids"
    TOTAL_PHOSPHORUS = "total_phosphorus"
    TOTAL_AMMONIA = "total_ammonia"
    BOD = "bod"

    @property
    def unit(self) -> str:
        return "mlL" if self is Parameter.SETTLEABLE_SOLIDS else "mgL"

    @property
    def is_nutrient(self) -> bool:
        return self in {Parameter.TOTAL_PHOSPHORUS, Parameter.TOTAL_AMMONIA}


class Basis(Enum):
    """How a limit is expressed, which decides what it is compared against."""

    CONCENTRATION = "concentration"
    MASS_PER_DAY = "mass_per_day"
    FEED_BASED = "feed_based"

    @property
    def needs_flow(self) -> bool:
        return self is Basis.MASS_PER_DAY

    @property
    def needs_feed(self) -> bool:
        return self is Basis.FEED_BASED


@dataclass(frozen=True, slots=True)
class Limit:
    """One number in the permit."""

    parameter: Parameter
    basis: Basis
    value: Decimal
    net: bool = True
    label: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.parameter, Parameter):
            raise ValidationError(f"{self.parameter!r} is not a parameter", field="parameter")
        if not isinstance(self.basis, Basis):
            raise ValidationError(f"{self.basis!r} is not a basis", field="basis")
        require_positive(self.value, field="value")

    @property
    def description(self) -> str:
        kind = "net" if self.net else "gross"
        return f"{kind} {self.parameter.value} {self.value} ({self.basis.value})"


@dataclass(frozen=True, slots=True)
class Sample:
    """One pair of readings, intake and outfall, on one day."""

    parameter: Parameter
    intake: Decimal
    outfall: Decimal
    flow: Quantity | None = None
    feed: Quantity | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.parameter, Parameter):
            raise ValidationError(f"{self.parameter!r} is not a parameter", field="parameter")
        require_non_negative(self.intake, field="intake")
        require_non_negative(self.outfall, field="outfall")

    @property
    def net(self) -> Decimal:
        """What the station added, which is never allowed to go below zero."""

        difference = self.outfall - self.intake
        return difference if difference > 0 else Decimal(0)

    @property
    def gross(self) -> Decimal:
        return self.outfall

    def value_for(self, limit: Limit) -> Decimal:
        """The number this sample offers against a limit."""

        if limit.parameter is not self.parameter:
            raise ValidationError(
                f"a {self.parameter.value} sample cannot answer a {limit.parameter.value} limit",
                field="parameter",
            )
        concentration = self.net if limit.net else self.gross
        if limit.basis is Basis.CONCENTRATION:
            return concentration
        if limit.basis is Basis.MASS_PER_DAY:
            if self.flow is None:
                raise ValidationError("a mass limit needs the flow", field="flow")
            litres = self.flow.to("Lpm").amount * Decimal(1440)
            return concentration * litres / Decimal(1_000_000)
        if self.feed is None:
            raise ValidationError("a feed based limit needs the feed", field="feed")
        fed = require_positive(self.feed.to("kg").amount, field="feed")
        litres = self.flow.to("Lpm").amount * Decimal(1440) if self.flow is not None else Decimal(0)
        if litres == 0:
            raise ValidationError("a feed based limit needs the flow", field="flow")
        mass = concentration * litres / Decimal(1_000_000)
        return safe_divide(mass, fed, field="feed")


def exceeds(sample: Sample, limit: Limit) -> bool:
    """Whether a sample is over a limit."""

    return sample.value_for(limit) > limit.value


def headroom(sample: Sample, limit: Limit) -> Decimal:
    """How far under a limit a sample sits, negative when it is over."""

    return limit.value - sample.value_for(limit)


def share_of_limit(sample: Sample, limit: Limit) -> Decimal:
    """The sample as a share of what the permit allows."""

    return safe_divide(sample.value_for(limit), limit.value, field="limit")


def feed_allowance(limit: Limit, feed: Quantity) -> Decimal:
    """The mass a feed based limit allows for a quantity of feed."""

    if limit.basis is not Basis.FEED_BASED:
        raise ValidationError("that limit is not written on feed", field="limit")
    kilograms = require_positive(feed.to("kg").amount, field="feed")
    return limit.value * kilograms


def net_removal(sample: Sample) -> Decimal:
    """The share of what came in that the station took out, when it did.

    Negative for the usual case where the station adds rather than removes, and
    it is worth reporting because a settling pond that is working shows up here
    before it shows up anywhere else.
    """

    if sample.intake == 0:
        raise ValidationError("nothing came in to remove", field="intake")
    return (sample.intake - sample.outfall) / sample.intake


def worst_of(samples: list[Sample], limit: Limit) -> Sample | None:
    """The sample that sits highest against a limit."""

    usable = [sample for sample in samples if sample.parameter is limit.parameter]
    if not usable:
        return None
    return max(usable, key=lambda sample: to_decimal(sample.value_for(limit)))


def limit_for(limits: list[Limit], parameter: Parameter, basis: Basis) -> Limit:
    """Find the one limit that covers a parameter on a basis."""

    matching = [limit for limit in limits if limit.parameter is parameter and limit.basis is basis]
    if not matching:
        raise ValidationError(
            f"the permit has no {basis.value} limit for {parameter.value}", field="limits"
        )
    if len(matching) > 1:
        raise ValidationError(
            f"the permit has two {basis.value} limits for {parameter.value}", field="limits"
        )
    return matching[0]
