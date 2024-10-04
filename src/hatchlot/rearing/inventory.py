"""The station inventory: every lot, where it is, and whether it adds up.

Three things are checked together here because they only mean something
together. What the lots say they hold. What the ledger says they hold. Whether
the unit each one is sitting in can carry it. A station can pass any two of
those and still be in trouble.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from ..calendar import parse_date
from ..errors import ValidationError
from ..numeric import Number, require_non_negative, safe_divide
from ..quantities.base import Quantity
from ..quantities.temperature import Temperature
from ..station import DEFAULT_PROFILE, StationProfile
from .container import ContainerRegister
from .ledger import Ledger
from .loading import Loading, LoadingStatus, assess
from .lot import RearingLot, total_biomass, total_population


@dataclass(frozen=True, slots=True)
class LotPosition:
    """One lot, where it is, and how that unit is sitting."""

    lot: str
    container: str
    population: Decimal
    biomass: Quantity
    ledger_population: Decimal
    loading: Loading | None

    @property
    def ledger_difference(self) -> Decimal:
        return self.population - self.ledger_population

    @property
    def agrees_with_ledger(self) -> bool:
        return self.ledger_difference == 0

    @property
    def status(self) -> LoadingStatus:
        return self.loading.status if self.loading is not None else LoadingStatus.OK


@dataclass(frozen=True, slots=True)
class Inventory:
    """The whole station, as of a day."""

    as_of: date
    positions: tuple[LotPosition, ...]
    population: Decimal
    biomass: Quantity
    homeless: tuple[str, ...]

    @property
    def disagreeing(self) -> tuple[LotPosition, ...]:
        return tuple(entry for entry in self.positions if not entry.agrees_with_ledger)

    @property
    def overloaded(self) -> tuple[LotPosition, ...]:
        return tuple(entry for entry in self.positions if entry.status is LoadingStatus.OVER)

    @property
    def warned(self) -> tuple[LotPosition, ...]:
        return tuple(entry for entry in self.positions if entry.status is LoadingStatus.WARNING)

    @property
    def is_clean(self) -> bool:
        return not (self.disagreeing or self.overloaded or self.homeless)

    def for_container(self, container: str) -> tuple[LotPosition, ...]:
        from ..identifiers import normalise_code

        code = normalise_code(container, field="container")
        return tuple(entry for entry in self.positions if entry.container == code)

    def line(self) -> str:
        return (
            f"{self.as_of.isoformat()}: {len(self.positions)} lots, "
            f"{self.population:.0f} fish, {self.biomass.rounded(0)}, "
            f"{len(self.disagreeing)} off the ledger, {len(self.overloaded)} overloaded"
        )


def take_inventory(
    lots: list[RearingLot],
    containers: ContainerRegister,
    ledger: Ledger,
    as_of: object,
    *,
    inflow_mgL: Number = "10.0",
    floor_mgL: Number = "6.0",
    temperature: Temperature | None = None,
    profile: StationProfile | None = None,
) -> Inventory:
    """Walk every live lot and check it three ways."""

    station = profile or DEFAULT_PROFILE
    when = parse_date(as_of)
    live = [lot for lot in lots if not lot.state.is_closed]
    codes = [str(lot.code) for lot in live]
    if len(set(codes)) != len(codes):
        raise ValidationError("the same lot is on the inventory twice", field="lots")
    positions: list[LotPosition] = []
    homeless: list[str] = []
    for lot in sorted(live, key=lambda entry: str(entry.code)):
        container = containers.find(lot.container)
        if container is None:
            homeless.append(str(lot.code))
            loading = None
        else:
            loading = assess(
                container,
                lot,
                inflow_mgL=inflow_mgL,
                floor_mgL=floor_mgL,
                temperature=temperature,
                profile=station,
            )
        positions.append(
            LotPosition(
                lot=str(lot.code),
                container=lot.container,
                population=lot.population,
                biomass=lot.biomass,
                ledger_population=ledger.balance(str(lot.code), as_of=when).closing,
                loading=loading,
            )
        )
    return Inventory(
        as_of=when,
        positions=tuple(positions),
        population=total_population(live),
        biomass=total_biomass(live),
        homeless=tuple(homeless),
    )


def biomass_by_container(inventory: Inventory) -> dict[str, Quantity]:
    """What each unit is carrying, across every lot in it."""

    totals: dict[str, Quantity] = {}
    for entry in inventory.positions:
        running = totals.get(entry.container, Quantity(0, "kg"))
        totals[entry.container] = running + entry.biomass
    return totals


def station_use(inventory: Inventory, containers: ContainerRegister) -> Decimal:
    """The share of the station's volume that has fish in it."""

    total = containers.total_volume().to("m3").amount
    if total <= 0:
        raise ValidationError("the station has no volume", field="containers")
    used = Decimal(0)
    for code in biomass_by_container(inventory):
        container = containers.find(code)
        if container is not None:
            used += container.volume.to("m3").amount
    return safe_divide(used, total, field="containers")


def average_density(inventory: Inventory, containers: ContainerRegister) -> Decimal:
    """Kilograms of fish per cubic metre across the units that are in use."""

    volume = Decimal(0)
    for code in biomass_by_container(inventory):
        container = containers.find(code)
        if container is not None:
            volume += container.volume.to("m3").amount
    if volume == 0:
        return Decimal(0)
    return require_non_negative(inventory.biomass.to("kg").amount, field="biomass") / volume
