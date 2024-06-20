"""Flow weighting, which three modules were each doing their own way.

Temperature, gas pressure and any other intensive property of a water mix by the
same rule: weight by flow, refuse an empty mix, refuse a mix with the valves
shut. Having that written three times meant three chances to weight by count
instead, so it is written once here and the callers pass a getter.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from decimal import Decimal
from typing import TypeVar

from ..errors import ValidationError
from ..quantities.base import Quantity

T = TypeVar("T")

BASE_FLOW_UNIT = "gpm"


def total_flow(items: Sequence[T], flow_of: Callable[[T], Quantity], symbol: str) -> Quantity:
    """Add the flows of a sequence, refusing a negative contribution."""

    total = Quantity(0, symbol)
    for item in items:
        flow = flow_of(item)
        if flow.amount < 0:
            raise ValidationError("a negative flow is not a contribution", field="flow")
        total = total + flow
    return total


def flow_weighted(
    items: Sequence[T],
    flow_of: Callable[[T], Quantity],
    value_of: Callable[[T], Decimal],
    *,
    what: str = "mix",
) -> Decimal:
    """The flow weighted mean of a property across a mix."""

    if not items:
        raise ValidationError(f"cannot blend nothing into a {what}", field="parts")
    total = Decimal(0)
    weighted = Decimal(0)
    for item in items:
        flow = flow_of(item)
        if flow.amount < 0:
            raise ValidationError("a negative flow is not a contribution", field="flow")
        share = flow.to(BASE_FLOW_UNIT).amount
        total += share
        weighted += share * value_of(item)
    if total == 0:
        raise ValidationError(f"a {what} with no flow has no value", field="parts")
    return weighted / total


def flow_share(
    items: Sequence[T],
    flow_of: Callable[[T], Quantity],
    matches: Callable[[T], bool],
) -> Decimal:
    """What fraction of a mix comes from the items that match."""

    total = Decimal(0)
    part = Decimal(0)
    for item in items:
        share = flow_of(item).to(BASE_FLOW_UNIT).amount
        if share < 0:
            raise ValidationError("a negative flow is not a contribution", field="flow")
        total += share
        if matches(item):
            part += share
    if total == 0:
        raise ValidationError("a mix with no flow has no fractions", field="parts")
    return part / total
