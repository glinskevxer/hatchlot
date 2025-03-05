"""Loading a truck, and getting the fish off it alive.

Three numbers decide a haul and they pull against each other. How many fish fit
in a tank, which falls as the trip gets longer and as the water gets warmer. How
much oxygen the trip needs, which rises with both. And how far apart the truck
water and the receiving water are allowed to be when the fish go over the side,
which is the one that gets skipped when a crew is running late.

The tempering rule is written here as a time rather than a yes or no, because
telling a driver he cannot stock is useless and telling him it will take forty
minutes is not.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum

from ..errors import PolicyError, ValidationError
from ..identifiers import normalise_code
from ..numeric import Number, require_positive, safe_divide, to_decimal
from ..quantities.base import Quantity
from ..quantities.temperature import Temperature, TemperatureSpan

# A tank will carry this weight of fish per litre on a short cold haul. Every
# other condition takes something off it.
BASE_DENSITY_KG_PER_L = Decimal("0.12")

# Oxygen a kilogram of fish uses on a truck in an hour, which is well above the
# resting rate because loading and hauling are not restful.
HAUL_OXYGEN_MG_PER_KG_HOUR = Decimal("450")


class OxygenSupply(Enum):
    """What the truck has on it."""

    AGITATOR = "agitator"
    BOTTLED = "bottled"
    LIQUID = "liquid"

    @property
    def can_be_topped_up(self) -> bool:
        return self is not OxygenSupply.AGITATOR


@dataclass(frozen=True, slots=True)
class Tank:
    """One tank on a truck."""

    code: str
    volume: Quantity
    supply: OxygenSupply

    def __post_init__(self) -> None:
        object.__setattr__(self, "code", normalise_code(self.code, field="tank"))
        require_positive(self.volume.to("L").amount, field="volume")
        if not isinstance(self.supply, OxygenSupply):
            raise ValidationError(f"{self.supply!r} is not an oxygen supply", field="supply")


def haul_density(hours: Number, water: Temperature) -> Decimal:
    """The kilograms of fish a litre of tank water will carry.

    Falls with the length of the trip and with the temperature, both of which
    are the same problem: the fish use the oxygen up faster than it goes in.
    """

    duration = require_positive(hours, field="hours")
    celsius = water.celsius
    if celsius <= 0:
        raise ValidationError("that is not haulable water", field="water")
    time_factor = Decimal(1) / (Decimal(1) + duration / Decimal(8))
    warm = celsius - Decimal(10)
    heat_factor = Decimal(1) if warm <= 0 else Decimal(1) - warm * Decimal("0.05")
    if heat_factor < Decimal("0.3"):
        heat_factor = Decimal("0.3")
    return BASE_DENSITY_KG_PER_L * time_factor * heat_factor


def tank_capacity(tank: Tank, hours: Number, water: Temperature) -> Quantity:
    """The biomass a tank will carry on a trip."""

    return Quantity(tank.volume.to("L").amount * haul_density(hours, water), "kg")


def oxygen_needed(biomass: Quantity, hours: Number) -> Quantity:
    """The oxygen a load uses over a trip, as a mass."""

    duration = require_positive(hours, field="hours")
    kilograms = require_positive(biomass.to("kg").amount, field="biomass")
    milligrams = kilograms * HAUL_OXYGEN_MG_PER_KG_HOUR * duration
    return Quantity(milligrams / Decimal(1_000_000), "kg")


@dataclass
class HaulLoad:
    """One truck, loaded."""

    code: str
    tanks: list[Tank]
    fish: Decimal
    mean_weight: Quantity
    hours: Decimal
    load_water: Temperature
    driver: str

    def __post_init__(self) -> None:
        self.code = normalise_code(self.code, field="haul")
        if not self.tanks:
            raise ValidationError("a haul needs a tank", field="tanks")
        codes = [tank.code for tank in self.tanks]
        if len(set(codes)) != len(codes):
            raise ValidationError("the same tank twice", field="tanks")
        self.fish = require_positive(self.fish, field="fish")
        require_positive(self.mean_weight.to("g").amount, field="mean_weight")
        self.hours = require_positive(self.hours, field="hours")
        if not self.driver.strip():
            raise ValidationError("a haul needs a driver", field="driver")
        self.driver = self.driver.strip()

    @property
    def biomass(self) -> Quantity:
        return Quantity(self.fish * self.mean_weight.to("kg").amount, "kg")

    @property
    def water_volume(self) -> Quantity:
        total = Quantity(0, "L")
        for tank in self.tanks:
            total = total + tank.volume
        return total

    @property
    def capacity(self) -> Quantity:
        return Quantity(
            self.water_volume.to("L").amount * haul_density(self.hours, self.load_water), "kg"
        )

    @property
    def loading_share(self) -> Decimal:
        return safe_divide(
            self.biomass.to("kg").amount, self.capacity.to("kg").amount, field="capacity"
        )

    @property
    def is_overloaded(self) -> bool:
        return self.biomass.to("kg").amount > self.capacity.to("kg").amount

    def oxygen(self) -> Quantity:
        return oxygen_needed(self.biomass, self.hours)

    def check(self) -> None:
        """Refuse a load the tanks will not carry."""

        if self.is_overloaded:
            raise PolicyError(
                f"haul {self.code} is carrying {self.biomass.rounded(0)} against a "
                f"capacity of {self.capacity.rounded(0)}",
                rule="haul.overloaded",
            )


def tempering_span(truck: Temperature, receiving: Temperature) -> TemperatureSpan:
    """How far apart the two waters are."""

    return abs(receiving - truck)


def tempering_minutes(
    truck: Temperature, receiving: Temperature, *, minutes_per_degree: Number = 10
) -> int:
    """How long the truck has to mix before the fish can go over the side."""

    rate = require_positive(minutes_per_degree, field="minutes_per_degree")
    gap = tempering_span(truck, receiving).to("C").degrees
    return int((abs(gap) * rate).to_integral_value(rounding="ROUND_CEILING"))


def check_tempering(
    truck: Temperature, receiving: Temperature, *, limit_celsius: Number = 2
) -> None:
    """Refuse a release across too big a temperature step."""

    allowed = require_positive(limit_celsius, field="limit_celsius")
    gap = abs(tempering_span(truck, receiving).to("C").degrees)
    if gap > allowed:
        raise PolicyError(
            f"the truck is {gap} degC off the receiving water, limit is {allowed}",
            rule="haul.tempering",
        )


def loads_needed(
    fish: Number, mean_weight: Quantity, tank: Tank, hours: Number, water: Temperature
) -> int:
    """How many truck loads a release will take."""

    count = require_positive(fish, field="fish")
    biomass = count * mean_weight.to("kg").amount
    per_load = tank_capacity(tank, hours, water).to("kg").amount
    if per_load <= 0:
        raise ValidationError("that tank carries nothing on this trip", field="tank")
    return int((to_decimal(biomass) / per_load).to_integral_value(rounding="ROUND_CEILING"))
