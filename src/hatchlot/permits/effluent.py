"""Estimating the discharge off the feed, before anybody samples it.

Sampling tells a station what it discharged last Tuesday. The feed record tells
it what it is going to discharge next month, because almost everything in a
hatchery effluent came out of a feed bag. That makes the estimate worth having:
it is the only version of the number that arrives in time to do anything about.

The coefficients are the usual ones for a salmonid feed, and they are exposed
because a station that has sampled its own outfall for a year should be using
its own.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from ..errors import ValidationError
from ..numeric import Number, require_non_negative, require_positive, safe_divide, to_decimal
from ..quantities.base import Quantity
from .limits import Basis, Limit, Parameter

# Kilograms produced per kilogram of feed fed, on a typical 45/16 salmonid feed.
SOLIDS_PER_FEED = Decimal("0.25")
PHOSPHORUS_PER_FEED = Decimal("0.0055")
NITROGEN_PER_FEED = Decimal("0.0385")


@dataclass(frozen=True, slots=True)
class Loading:
    """What a month of feeding is expected to put down the pipe."""

    feed: Quantity
    solids: Quantity
    phosphorus: Quantity
    nitrogen: Quantity

    @property
    def total(self) -> Quantity:
        return self.solids + self.phosphorus + self.nitrogen

    def per_day(self, days: int) -> Quantity:
        if days < 1:
            raise ValidationError("a loading is over days", field="days")
        return Quantity(self.solids.to("kg").amount / Decimal(days), "kg")


def estimate_loading(
    feed: Quantity,
    *,
    solids_share: Number = SOLIDS_PER_FEED,
    phosphorus_share: Number = PHOSPHORUS_PER_FEED,
    nitrogen_share: Number = NITROGEN_PER_FEED,
) -> Loading:
    """Work the expected discharge out of the feed that was fed."""

    kilograms = require_non_negative(feed.to("kg").amount, field="feed")
    shares = []
    for name, value in (
        ("solids_share", solids_share),
        ("phosphorus_share", phosphorus_share),
        ("nitrogen_share", nitrogen_share),
    ):
        share = require_non_negative(value, field=name)
        if share > 1:
            raise ValidationError(f"{name} over one is not a share", field=name)
        shares.append(share)
    return Loading(
        feed=feed,
        solids=Quantity(kilograms * shares[0], "kg"),
        phosphorus=Quantity(kilograms * shares[1], "kg"),
        nitrogen=Quantity(kilograms * shares[2], "kg"),
    )


def concentration_from(mass: Quantity, flow: Quantity, days: int) -> Decimal:
    """The mg/L a mass of discharge comes to at a flow over a stretch of days."""

    if days < 1:
        raise ValidationError("a concentration is over days", field="days")
    litres = require_positive(flow.to("Lpm").amount, field="flow") * Decimal(1440 * days)
    milligrams = mass.to("kg").amount * Decimal(1_000_000)
    return safe_divide(milligrams, litres, field="flow")


def feed_ceiling(
    limit: Limit, flow: Quantity, days: int, *, share: Number = SOLIDS_PER_FEED
) -> Quantity:
    """The most feed a station can feed and still meet a concentration limit.

    This is the number that turns a permit into a production plan, because it
    says how many fish the station can carry before the pipe becomes the
    constraint rather than the water.
    """

    if limit.basis is not Basis.CONCENTRATION:
        raise ValidationError("that limit is not a concentration", field="limit")
    if days < 1:
        raise ValidationError("a ceiling is over days", field="days")
    fraction = require_positive(share, field="share")
    litres = require_positive(flow.to("Lpm").amount, field="flow") * Decimal(1440 * days)
    allowed_mass = limit.value * litres / Decimal(1_000_000)
    return Quantity(allowed_mass / fraction, "kg")


def parameter_mass(loading: Loading, parameter: Parameter) -> Quantity:
    """The part of a loading that answers to one permit parameter."""

    if parameter in {Parameter.SETTLEABLE_SOLIDS, Parameter.SUSPENDED_SOLIDS}:
        return loading.solids
    if parameter is Parameter.TOTAL_PHOSPHORUS:
        return loading.phosphorus
    if parameter is Parameter.TOTAL_AMMONIA:
        return loading.nitrogen
    raise ValidationError(f"the feed model says nothing about {parameter.value}", field="parameter")


def projected_against(loading: Loading, limit: Limit, flow: Quantity, days: int) -> Decimal:
    """The projected reading against a concentration limit, as a share of it."""

    if limit.basis is not Basis.CONCENTRATION:
        raise ValidationError("that limit is not a concentration", field="limit")
    mass = parameter_mass(loading, limit.parameter)
    return safe_divide(concentration_from(mass, flow, days), to_decimal(limit.value), field="limit")
