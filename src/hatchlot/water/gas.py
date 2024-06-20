"""Total dissolved gas, and the pressure difference that hurts fish.

A well that comes up under pressure, or a pump that pulls air in on the suction
side, leaves water carrying more gas than the atmosphere can hold in it. The
fish do not care about the percentage, they care about the difference between
the gas pressure in the water and the pressure outside it, and they get some of
that difference back by swimming deeper.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum

from ..errors import ValidationError
from ..numeric import Number, require_non_negative, require_positive, to_decimal
from ..quantities.base import Quantity
from .blending import flow_weighted

MMHG_PER_METRE_OF_WATER = Decimal("73.42")


class GasRisk(Enum):
    """What a delta P means for a rearing unit, in the order it gets worse."""

    SAFE = "safe"
    WATCH = "watch"
    HAZARD = "hazard"

    @property
    def is_actionable(self) -> bool:
        return self is not GasRisk.SAFE


@dataclass(frozen=True, slots=True)
class GasReading:
    """One saturometer reading against the barometer it was taken under."""

    total_gas_mmHg: Decimal
    barometric_mmHg: Decimal
    depth_m: Decimal = Decimal(0)

    def __init__(self, total_gas_mmHg: Number, barometric_mmHg: Number, depth_m: Number = 0):
        object.__setattr__(
            self, "total_gas_mmHg", require_positive(total_gas_mmHg, field="total_gas")
        )
        object.__setattr__(
            self, "barometric_mmHg", require_positive(barometric_mmHg, field="barometric")
        )
        object.__setattr__(self, "depth_m", require_non_negative(depth_m, field="depth_m"))

    @property
    def percent(self) -> Decimal:
        """Total dissolved gas as a percentage of the local atmosphere."""

        return self.total_gas_mmHg / self.barometric_mmHg * Decimal(100)

    @property
    def delta_p(self) -> Decimal:
        """The uncompensated pressure difference in mmHg, positive when over."""

        return self.total_gas_mmHg - self.barometric_mmHg

    @property
    def compensated_delta_p(self) -> Decimal:
        """Delta P with the depth of water the fish can hold under taken off.

        A metre of water is worth about 73 mmHg, so a deep raceway carries a
        supersaturation that would be a problem in a shallow trough.
        """

        return self.delta_p - self.depth_m * MMHG_PER_METRE_OF_WATER

    @property
    def is_supersaturated(self) -> bool:
        return self.delta_p > 0

    def risk(self, *, watch_at: Number = 25, hazard_at: Number = 76) -> GasRisk:
        """Classify the compensated reading against two thresholds in mmHg."""

        watch = to_decimal(watch_at, field="watch_at")
        hazard = to_decimal(hazard_at, field="hazard_at")
        if watch > hazard:
            raise ValidationError("the watch level is above the hazard level", field="watch_at")
        compensated = self.compensated_delta_p
        if compensated >= hazard:
            return GasRisk.HAZARD
        if compensated >= watch:
            return GasRisk.WATCH
        return GasRisk.SAFE


def compensation_depth(delta_p_mmHg: Number) -> Quantity:
    """How deep the water must be for a delta P to be held down to zero."""

    delta = to_decimal(delta_p_mmHg, field="delta_p")
    if delta <= 0:
        return Quantity(0, "m")
    return Quantity(delta / MMHG_PER_METRE_OF_WATER, "m")


def blended_delta_p(readings: list[tuple[GasReading, Quantity]]) -> Decimal:
    """Flow weighted delta P where two waters are mixed.

    Gas pressures do not average by volume exactly, but flow weighting is what
    every station does on paper and it is right to within the reading error.
    """

    return flow_weighted(
        readings,
        lambda pair: pair[1],
        lambda pair: pair[0].delta_p,
        what="gas blend",
    )
