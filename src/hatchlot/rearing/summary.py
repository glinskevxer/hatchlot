"""One reading of the rearing side, for a morning report.

The inventory answers what is there. This answers how it is going, which needs
the mortality log and the cleaning log as well, and it deliberately reports the
mortality as a rate over a window rather than a total, because a total tells you
nothing without knowing how long it took and how many fish there were.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from ..calendar import DateRange
from ..errors import ValidationError
from ..numeric import Number, require_positive, safe_divide
from ..quantities.base import Quantity
from .cleaning import CleaningLog
from .container import ContainerRegister
from .inventory import Inventory, biomass_by_container
from .mortality import MortalityCause, MortalityLog


@dataclass(frozen=True, slots=True)
class RearingSummary:
    """How the rearing units are doing over a window."""

    window: DateRange
    lots: int
    population: Decimal
    biomass: Quantity
    dead: Decimal
    mortality_rate: Decimal
    preventable_share: Decimal
    overloaded: tuple[str, ...]
    warned: tuple[str, ...]
    overdue_cleaning: tuple[str, ...]
    worst_cause: MortalityCause | None

    @property
    def survival(self) -> Decimal:
        return Decimal(1) - self.mortality_rate

    @property
    def needs_attention(self) -> bool:
        return bool(self.overloaded or self.overdue_cleaning)

    def line(self) -> str:
        return (
            f"{self.window}: {self.lots} lots, {self.population:.0f} fish, "
            f"{self.mortality_rate:.2%} lost, {len(self.overloaded)} over, "
            f"{len(self.overdue_cleaning)} to clean"
        )


def summarise_rearing(
    inventory: Inventory,
    mortality: MortalityLog,
    cleaning: CleaningLog,
    containers: ContainerRegister,
    window: DateRange,
) -> RearingSummary:
    """Pull the rearing side together over a window."""

    dead = Decimal(0)
    causes: dict[MortalityCause, Decimal] = {}
    for position in inventory.positions:
        dead += mortality.total(position.lot, window)
        for cause, count in mortality.by_cause(position.lot, window).items():
            causes[cause] = causes.get(cause, Decimal(0)) + count
    exposed = inventory.population + dead
    rate = safe_divide(dead, exposed, field="population") if exposed > 0 else Decimal(0)
    preventable = sum(
        (count for cause, count in causes.items() if cause.is_preventable), Decimal(0)
    )
    loads = biomass_by_container(inventory)
    overdue = []
    for code, biomass in sorted(loads.items()):
        container = containers.find(code)
        if container is None:
            continue
        if cleaning.is_overdue(container, biomass, window.end):
            overdue.append(code)
    return RearingSummary(
        window=window,
        lots=len(inventory.positions),
        population=inventory.population,
        biomass=inventory.biomass,
        dead=dead,
        mortality_rate=rate,
        preventable_share=(
            safe_divide(preventable, dead, field="dead") if dead > 0 else Decimal(0)
        ),
        overloaded=tuple(entry.container for entry in inventory.overloaded),
        warned=tuple(entry.container for entry in inventory.warned),
        overdue_cleaning=tuple(overdue),
        worst_cause=max(causes, key=lambda cause: causes[cause]) if causes else None,
    )


def projected_biomass(summary: RearingSummary, daily_growth: Number, days: int) -> Quantity:
    """What the station will be carrying in a few days at a growth rate."""

    if days < 0:
        raise ValidationError("cannot project backwards", field="days")
    growth = require_positive(daily_growth, field="daily_growth")
    factor = (Decimal(1) + growth) ** days
    return Quantity(summary.biomass.to("kg").amount * factor, "kg")


def days_of_feed(summary: RearingSummary, on_hand: Quantity, daily_share: Number) -> int:
    """How many days of feeding the store will cover at a feeding rate."""

    share = require_positive(daily_share, field="daily_share")
    daily = summary.biomass.to("kg").amount * share
    if daily <= 0:
        raise ValidationError("nothing is being fed", field="biomass")
    return int((on_hand.to("kg").amount / daily).to_integral_value(rounding="ROUND_FLOOR"))
