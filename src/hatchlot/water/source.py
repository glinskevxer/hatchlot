"""The water sources a station runs on, and what happens when they are mixed.

Almost nothing at a hatchery runs on one water. A spring holds a steady
temperature and runs short in August, a well is colder and gas supersaturated,
and the creek is whatever the weather made it. Rearing units get a blend, and
the blend is what every downstream rule has to be worked out against.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum

from ..errors import ValidationError
from ..identifiers import normalise_code
from ..numeric import require_non_negative, require_range
from ..quantities.base import Quantity
from ..quantities.temperature import Temperature
from ..registry import CodeRegistry
from .blending import flow_share, total_flow


class SourceKind(Enum):
    """Where the water comes from, which decides what it is likely to do."""

    SPRING = "spring"
    WELL = "well"
    SURFACE = "surface"
    REUSE = "reuse"
    MUNICIPAL = "municipal"

    @property
    def is_pathogen_bearing(self) -> bool:
        """Surface and reused water can carry a pathogen into a clean lot."""

        return self in {SourceKind.SURFACE, SourceKind.REUSE}


@dataclass(frozen=True, slots=True)
class WaterSource:
    """One supply, with the flow it is rated for and how it behaves."""

    code: str
    name: str
    kind: SourceKind
    design_flow: Quantity
    minimum_flow: Quantity | None = None
    gas_supersaturated: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "code", normalise_code(self.code, field="source"))
        if not self.name.strip():
            raise ValidationError("a water source needs a name", field="name")
        object.__setattr__(self, "name", self.name.strip())
        if not isinstance(self.kind, SourceKind):
            raise ValidationError(f"{self.kind!r} is not a source kind", field="kind")
        require_non_negative(self.design_flow.amount, field="design_flow")
        if self.minimum_flow is not None and self.minimum_flow > self.design_flow:
            raise ValidationError(
                "the minimum flow cannot be above the design flow", field="minimum_flow"
            )

    @property
    def dependable_flow(self) -> Quantity:
        """What the station can count on: the minimum if one is recorded."""

        return self.minimum_flow if self.minimum_flow is not None else self.design_flow

    def shortfall_against(self, demand: Quantity) -> Quantity:
        """How much more water a demand needs than this source can be relied on for."""

        deficit = demand.to(self.dependable_flow.symbol) - self.dependable_flow
        floor = Quantity(0, deficit.symbol)
        return deficit if deficit > floor else floor


@dataclass(frozen=True, slots=True)
class BlendPart:
    """One contribution to a blend: a flow off a source at a temperature."""

    source: str
    flow: Quantity
    temperature: Temperature

    def __post_init__(self) -> None:
        object.__setattr__(self, "source", normalise_code(self.source, field="source"))
        require_non_negative(self.flow.amount, field="flow")


def blend_temperature(parts: list[BlendPart], scale: str = "C") -> Temperature:
    """The flow weighted temperature of a mix.

    Weighted by flow, not by count, which is the mistake that puts a raceway two
    degrees off its recipe when a small cold well is opened into a big spring.
    """

    if not parts:
        raise ValidationError("cannot blend nothing", field="parts")
    symbol = parts[0].flow.symbol
    total = Decimal(0)
    weighted = Decimal(0)
    for part in parts:
        flow = part.flow.to(symbol).amount
        total += flow
        weighted += flow * part.temperature.to(scale).value
    if total == 0:
        raise ValidationError("a blend with no flow has no temperature", field="parts")
    return Temperature(weighted / total, scale)


def blend_flow(parts: list[BlendPart], symbol: str = "gpm") -> Quantity:
    """The total flow of a blend, in one unit."""

    total = Quantity(0, symbol)
    for part in parts:
        total = total + part.flow
    return total


def mix_fraction(parts: list[BlendPart], source: str) -> Decimal:
    """What share of a blend comes off one source, as a fraction of the total."""

    code = normalise_code(source, field="source")
    total = blend_flow(parts).amount
    if total == 0:
        raise ValidationError("a blend with no flow has no fractions", field="parts")
    share = sum((part.flow.to("gpm").amount for part in parts if part.source == code), Decimal(0))
    return share / total


class SourceRegister(CodeRegistry[WaterSource]):
    """The station's water supplies, keyed by code."""

    def __init__(self) -> None:
        super().__init__("water source", lambda source: source.code)

    def of_kind(self, kind: SourceKind) -> tuple[WaterSource, ...]:
        return self.where(lambda source: source.kind is kind)

    def total_dependable_flow(self, symbol: str = "gpm") -> Quantity:
        return total_flow(self.all(), lambda source: source.dependable_flow, symbol)

    def reuse_fraction(self) -> Decimal:
        """How much of the station's dependable water has been through fish already."""

        if self.total_dependable_flow().amount == 0:
            return Decimal(0)
        share = flow_share(
            self.all(),
            lambda source: source.dependable_flow,
            lambda source: source.kind is SourceKind.REUSE,
        )
        return require_range(share, 0, 1, field="reuse_fraction")
