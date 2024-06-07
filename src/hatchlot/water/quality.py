"""The rest of the water chemistry a hatchery has to watch.

Ammonia is the one that matters and it is the one people get wrong, because the
number a kit reports is total ammonia nitrogen and the number that kills fish is
the un-ionised fraction of it. That fraction is a function of pH and
temperature, and it roughly doubles for every rise of a third of a pH unit, so a
tank that is fine at pH 7 is dangerous at pH 8 on the same reading.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from decimal import Decimal
from enum import Enum

from ..errors import ValidationError
from ..numeric import Number, require_non_negative, require_range, to_decimal
from ..quantities.temperature import Temperature


class QualityFlag(Enum):
    """How a reading sits against the station's limits."""

    OK = "ok"
    MARGINAL = "marginal"
    OVER = "over"


def ammonia_pka(temperature: Temperature) -> Decimal:
    """The ammonia dissociation constant at a water temperature."""

    kelvin = float(temperature.celsius) + 273.15
    if kelvin <= 0:
        raise ValidationError("temperature is at absolute zero", field="temperature")
    return to_decimal(round(0.09018 + 2729.92 / kelvin, 6), field="pka")


def unionised_fraction(ph: Number, temperature: Temperature) -> Decimal:
    """The share of total ammonia that is un-ionised, between 0 and 1."""

    acidity = require_range(ph, 4, 11, field="ph")
    exponent = float(ammonia_pka(temperature) - acidity)
    return to_decimal(round(1.0 / (1.0 + math.pow(10.0, exponent)), 8), field="fraction")


def unionised_ammonia(total_ammonia_mgL: Number, ph: Number, temperature: Temperature) -> Decimal:
    """Un-ionised ammonia in mg/L as nitrogen, the number the limit is written on."""

    total = require_non_negative(total_ammonia_mgL, field="total_ammonia")
    return total * unionised_fraction(ph, temperature)


def total_ammonia_ceiling(
    limit_unionised_mgL: Number, ph: Number, temperature: Temperature
) -> Decimal:
    """The total ammonia reading that just reaches an un-ionised limit.

    This is the number to put on a wall chart, because nobody in a hatchery
    measures un-ionised ammonia directly.
    """

    limit = require_non_negative(limit_unionised_mgL, field="limit")
    fraction = unionised_fraction(ph, temperature)
    if fraction == 0:
        raise ValidationError("no un-ionised fraction at this pH", field="ph")
    return limit / fraction


def nitrite_chloride_ratio(nitrite_mgL: Number, chloride_mgL: Number) -> Decimal:
    """Nitrite against the chloride that protects the fish from it."""

    nitrite = require_non_negative(nitrite_mgL, field="nitrite")
    chloride = require_non_negative(chloride_mgL, field="chloride")
    if chloride == 0:
        raise ValidationError("no chloride to protect against nitrite", field="chloride")
    return nitrite / chloride


@dataclass(frozen=True, slots=True)
class QualityLimits:
    """A station's own thresholds, in the units the readings arrive in."""

    unionised_ammonia_mgL: Decimal = Decimal("0.0125")
    nitrite_chloride_ratio: Decimal = Decimal("0.10")
    ph_low: Decimal = Decimal("6.5")
    ph_high: Decimal = Decimal("8.5")
    marginal_share: Decimal = Decimal("0.8")

    def __post_init__(self) -> None:
        if self.ph_low >= self.ph_high:
            raise ValidationError("the pH band is inverted", field="ph_low")
        if not 0 < self.marginal_share <= 1:
            raise ValidationError("the marginal share is a fraction of the limit", field="marginal")

    def flag_against(self, value: Number, limit: Decimal) -> QualityFlag:
        """Classify one reading against one limit."""

        reading = to_decimal(value, field="reading")
        if reading > limit:
            return QualityFlag.OVER
        if reading >= limit * self.marginal_share:
            return QualityFlag.MARGINAL
        return QualityFlag.OK


@dataclass(frozen=True, slots=True)
class WaterQuality:
    """One set of chemistry readings off a rearing unit."""

    ph: Decimal
    temperature: Temperature
    total_ammonia_mgL: Decimal
    nitrite_mgL: Decimal = Decimal(0)
    chloride_mgL: Decimal = Decimal(0)
    alkalinity_mgL: Decimal = Decimal(0)
    hardness_mgL: Decimal = Decimal(0)

    def __post_init__(self) -> None:
        object.__setattr__(self, "ph", require_range(self.ph, 4, 11, field="ph"))
        for field in ("total_ammonia_mgL", "nitrite_mgL", "chloride_mgL"):
            object.__setattr__(self, field, require_non_negative(getattr(self, field), field=field))

    @property
    def unionised_ammonia_mgL(self) -> Decimal:
        return unionised_ammonia(self.total_ammonia_mgL, self.ph, self.temperature)

    def flags(self, limits: QualityLimits | None = None) -> dict[str, QualityFlag]:
        """Every reading classified, keyed by what it is."""

        rules = limits or QualityLimits()
        result = {
            "ammonia": rules.flag_against(self.unionised_ammonia_mgL, rules.unionised_ammonia_mgL)
        }
        if self.chloride_mgL > 0:
            result["nitrite"] = rules.flag_against(
                nitrite_chloride_ratio(self.nitrite_mgL, self.chloride_mgL),
                rules.nitrite_chloride_ratio,
            )
        if self.ph < rules.ph_low or self.ph > rules.ph_high:
            result["ph"] = QualityFlag.OVER
        else:
            result["ph"] = QualityFlag.OK
        return result

    def worst_flag(self, limits: QualityLimits | None = None) -> QualityFlag:
        order = [QualityFlag.OK, QualityFlag.MARGINAL, QualityFlag.OVER]
        return max(self.flags(limits).values(), key=order.index)
