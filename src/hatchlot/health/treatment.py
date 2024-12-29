"""Chemical treatments, and the two ways of working out how much to put in.

A static bath is simple: the concentration times the volume of water standing in
the unit. A flush into a flowing raceway is not, because the water is leaving
while you pour, so the amount depends on the flow and how long the treatment is
meant to last. Doing the static sum on a flowing raceway is how a station kills
a lot of fish, so the two are separate functions with separate names.

Both are then checked against a safety ceiling that moves with the water
temperature, because the same concentration of formalin that is routine at eight
degrees is dangerous at sixteen.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum

from ..errors import PolicyError, ValidationError
from ..numeric import Number, require_positive, to_decimal
from ..quantities.base import Quantity
from ..quantities.temperature import Temperature


class Chemical(Enum):
    """The compounds a hatchery puts in the water."""

    FORMALIN = "formalin"
    HYDROGEN_PEROXIDE = "hydrogen_peroxide"
    SALT = "salt"
    CHLORAMINE_T = "chloramine_t"
    IODOPHOR = "iodophor"

    @property
    def consumes_oxygen(self) -> bool:
        """Formalin takes oxygen out of the water as it works."""

        return self is Chemical.FORMALIN

    @property
    def safe_ppm_at_ten(self) -> Decimal:
        """The concentration a station will run at ten degrees, in ppm."""

        return {
            "formalin": Decimal(250),
            "hydrogen_peroxide": Decimal(500),
            "salt": Decimal(30000),
            "chloramine_t": Decimal(20),
            "iodophor": Decimal(100),
        }[self.value]

    @property
    def temperature_derate(self) -> Decimal:
        """How much of the ceiling is lost per degree above ten."""

        return {
            "formalin": Decimal("0.06"),
            "hydrogen_peroxide": Decimal("0.04"),
            "salt": Decimal(0),
            "chloramine_t": Decimal("0.02"),
            "iodophor": Decimal(0),
        }[self.value]


class Method(Enum):
    """How the chemical is delivered."""

    STATIC = "static"
    FLUSH = "flush"
    CONSTANT = "constant"

    @property
    def needs_flow(self) -> bool:
        return self is not Method.STATIC


def safe_ceiling(chemical: Chemical, water: Temperature) -> Decimal:
    """The highest concentration a station will run at this temperature."""

    if not isinstance(chemical, Chemical):
        raise ValidationError(f"{chemical!r} is not a chemical", field="chemical")
    celsius = water.celsius
    over = celsius - Decimal(10)
    if over <= 0:
        return chemical.safe_ppm_at_ten
    factor = Decimal(1) - chemical.temperature_derate * over
    if factor < Decimal("0.2"):
        factor = Decimal("0.2")
    return chemical.safe_ppm_at_ten * factor


def check_concentration(chemical: Chemical, concentration_ppm: Number, water: Temperature) -> None:
    """Refuse a concentration over the ceiling for this water."""

    wanted = require_positive(concentration_ppm, field="concentration_ppm")
    ceiling = safe_ceiling(chemical, water)
    if wanted > ceiling:
        raise PolicyError(
            f"{wanted} ppm of {chemical.value} is over the {ceiling} ppm ceiling at "
            f"{water.rounded(1)}",
            rule="treatment.concentration",
        )


def static_dose(concentration_ppm: Number, volume: Quantity) -> Quantity:
    """The chemical a standing volume of water needs, as a mass."""

    ppm = require_positive(concentration_ppm, field="concentration_ppm")
    litres = require_positive(volume.to("L").amount, field="volume")
    return Quantity(ppm * litres / Decimal(1_000_000), "kg")


def flush_dose(concentration_ppm: Number, flow: Quantity, minutes: Number) -> Quantity:
    """The chemical a flowing unit needs to hold a concentration for a time."""

    ppm = require_positive(concentration_ppm, field="concentration_ppm")
    per_minute = require_positive(flow.to("Lpm").amount, field="flow")
    duration = require_positive(minutes, field="minutes")
    litres = per_minute * duration
    return Quantity(ppm * litres / Decimal(1_000_000), "kg")


@dataclass(frozen=True, slots=True)
class Treatment:
    """One planned treatment of one unit."""

    lot: str
    chemical: Chemical
    method: Method
    concentration_ppm: Decimal
    minutes: Decimal
    water: Temperature
    volume: Quantity | None = None
    flow: Quantity | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.chemical, Chemical):
            raise ValidationError(f"{self.chemical!r} is not a chemical", field="chemical")
        if not isinstance(self.method, Method):
            raise ValidationError(f"{self.method!r} is not a method", field="method")
        require_positive(self.concentration_ppm, field="concentration_ppm")
        require_positive(self.minutes, field="minutes")
        if self.method.needs_flow and self.flow is None:
            raise ValidationError("a flowing treatment needs a flow", field="flow")
        if self.method is Method.STATIC and self.volume is None:
            raise ValidationError("a static bath needs a volume", field="volume")

    @property
    def dose(self) -> Quantity:
        """The chemical the treatment takes, by whichever sum applies."""

        if self.method is Method.STATIC:
            assert self.volume is not None
            return static_dose(self.concentration_ppm, self.volume)
        assert self.flow is not None
        return flush_dose(self.concentration_ppm, self.flow, self.minutes)

    @property
    def exposure(self) -> Decimal:
        """Concentration times time, which is what actually kills the parasite."""

        return self.concentration_ppm * self.minutes

    def check(self) -> None:
        check_concentration(self.chemical, self.concentration_ppm, self.water)

    def is_equivalent_to(self, other: Treatment, *, tolerance: Number = "0.1") -> bool:
        """Whether two treatments deliver the same exposure.

        Half the concentration for twice as long is the same product and not the
        same treatment, so this compares the product and nothing else.
        """

        share = to_decimal(tolerance, field="tolerance")
        if share < 0:
            raise ValidationError("a tolerance cannot be negative", field="tolerance")
        if self.exposure == 0:
            return False
        difference = abs(self.exposure - other.exposure) / self.exposure
        return difference <= share


def oxygen_headroom_needed(treatment: Treatment) -> Decimal:
    """Milligrams per litre of oxygen a treatment will take out of the water.

    Only formalin does this at a scale worth planning for, and the rule of thumb
    is a milligram per litre for every hundred parts per million.
    """

    if not treatment.chemical.consumes_oxygen:
        return Decimal(0)
    return treatment.concentration_ppm / Decimal(100)


def check_oxygen(treatment: Treatment, inflow_mgL: Number, floor_mgL: Number) -> None:
    """Refuse a treatment that would take the unit below its oxygen floor."""

    inflow = require_positive(inflow_mgL, field="inflow_mgL")
    floor = require_positive(floor_mgL, field="floor_mgL")
    cost = oxygen_headroom_needed(treatment)
    if inflow - cost < floor:
        raise PolicyError(
            f"the treatment would take the unit to {inflow - cost} mg/L, under {floor}",
            rule="treatment.oxygen",
        )
