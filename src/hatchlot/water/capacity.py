"""How much fish a rearing unit can carry, and which rule is the one that binds.

Three separate limits sit on every unit and they are not the same limit. Oxygen
says how much biomass the water can breathe for. The flow index says how much
water has to pass a fish of a given length regardless of oxygen. The density
index says how crowded the box is. A unit is at capacity when the first of the
three runs out, and knowing which one it was is what decides whether the answer
is more water, a bigger box or a split.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from decimal import Decimal
from enum import Enum

from ..errors import ValidationError
from ..numeric import Number, require_positive, to_decimal
from ..quantities.base import Quantity
from ..quantities.temperature import Temperature

# A fitted oxygen consumption model: mg of oxygen per kilogram of fish per hour,
# falling with fish size and rising with temperature. The coefficients are the
# ones a coldwater station would fit to its own trays; they are exposed so a
# station that has measured its own can pass them in.
CONSUMPTION_SCALE = Decimal("249")
CONSUMPTION_SIZE_EXPONENT = Decimal("-0.194")
CONSUMPTION_TEMPERATURE_COEFFICIENT = Decimal("0.064")


class BindingLimit(Enum):
    """Which of the three limits ran out first."""

    OXYGEN = "oxygen"
    FLOW_INDEX = "flow_index"
    DENSITY_INDEX = "density_index"


def oxygen_consumption_rate(
    temperature: Temperature,
    fish_weight_g: Number,
    *,
    scale: Number = CONSUMPTION_SCALE,
    size_exponent: Number = CONSUMPTION_SIZE_EXPONENT,
    temperature_coefficient: Number = CONSUMPTION_TEMPERATURE_COEFFICIENT,
) -> Decimal:
    """Milligrams of oxygen a kilogram of fish uses in an hour.

    Small fish breathe harder per unit of weight than big ones, which is why the
    size exponent is negative, and everything breathes harder when it is warm.
    """

    weight = require_positive(fish_weight_g, field="fish_weight_g")
    celsius = float(temperature.celsius)
    rate = (
        float(to_decimal(scale, field="scale"))
        * math.pow(float(weight), float(to_decimal(size_exponent, field="size_exponent")))
        * math.exp(float(to_decimal(temperature_coefficient)) * celsius)
    )
    return to_decimal(round(rate, 4), field="consumption")


def oxygen_limited_biomass(
    flow: Quantity,
    inflow_mgL: Number,
    floor_mgL: Number,
    temperature: Temperature,
    fish_weight_g: Number,
) -> Quantity:
    """The biomass in kilograms the oxygen in a flow will support."""

    inflow = to_decimal(inflow_mgL, field="inflow")
    floor = to_decimal(floor_mgL, field="floor")
    if floor >= inflow:
        raise ValidationError("no oxygen headroom above the floor", field="floor")
    litres_per_hour = flow.to("Lpm").amount * Decimal(60)
    if litres_per_hour <= 0:
        raise ValidationError("no flow carries no fish", field="flow")
    milligrams_available = litres_per_hour * (inflow - floor)
    rate = oxygen_consumption_rate(temperature, fish_weight_g)
    return Quantity(milligrams_available / rate, "kg")


def flow_limited_biomass(flow: Quantity, length: Quantity, flow_index: Number) -> Quantity:
    """Pounds the flow index allows: index times flow in gpm times length in inches."""

    index = require_positive(flow_index, field="flow_index")
    inches = require_positive(length.to("in").amount, field="length")
    gpm = require_positive(flow.to("gpm").amount, field="flow")
    return Quantity(index * gpm * inches, "lb")


def density_limited_biomass(volume: Quantity, length: Quantity, density_index: Number) -> Quantity:
    """Pounds the density index allows: index times volume in cubic feet times length."""

    index = require_positive(density_index, field="density_index")
    inches = require_positive(length.to("in").amount, field="length")
    cubic_feet = require_positive(volume.to("ft3").amount, field="volume")
    return Quantity(index * cubic_feet * inches, "lb")


@dataclass(frozen=True, slots=True)
class Capacity:
    """The three limits, and the one that binds."""

    oxygen: Quantity
    flow_index: Quantity
    density_index: Quantity
    binding: BindingLimit

    @property
    def allowed(self) -> Quantity:
        """The biomass the unit may actually carry, in pounds."""

        return {
            BindingLimit.OXYGEN: self.oxygen,
            BindingLimit.FLOW_INDEX: self.flow_index,
            BindingLimit.DENSITY_INDEX: self.density_index,
        }[self.binding].to("lb")

    def headroom(self, current: Quantity) -> Quantity:
        """What is left before the binding limit, negative when it is over."""

        return self.allowed - current.to("lb")

    def is_over(self, current: Quantity) -> bool:
        return current.to("lb") > self.allowed


def carrying_capacity(
    *,
    flow: Quantity,
    volume: Quantity,
    length: Quantity,
    inflow_mgL: Number,
    floor_mgL: Number,
    temperature: Temperature,
    fish_weight_g: Number,
    flow_index: Number,
    density_index: Number,
) -> Capacity:
    """Work all three limits and report which one runs out first."""

    oxygen = oxygen_limited_biomass(flow, inflow_mgL, floor_mgL, temperature, fish_weight_g).to(
        "lb"
    )
    by_flow = flow_limited_biomass(flow, length, flow_index)
    by_density = density_limited_biomass(volume, length, density_index)
    ranked = [
        (oxygen.amount, BindingLimit.OXYGEN),
        (by_flow.amount, BindingLimit.FLOW_INDEX),
        (by_density.amount, BindingLimit.DENSITY_INDEX),
    ]
    binding = min(ranked, key=lambda pair: pair[0])[1]
    return Capacity(oxygen=oxygen, flow_index=by_flow, density_index=by_density, binding=binding)
