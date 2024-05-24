"""Dissolved oxygen: what the water can hold, and what is left for the fish.

Everything a raceway can carry comes back to this. Cold water holds more
oxygen than warm water, a station at altitude holds less than one at sea level
because there is less atmosphere pressing on it, and the fish only get the
difference between what comes in and the floor the station refuses to go below.

The solubility table is the standard fresh water table at 760 mmHg. Values
between whole degrees are interpolated, which is close enough over a one degree
step and honest about being a table rather than an equation.
"""

from __future__ import annotations

import math
from decimal import Decimal

from ..errors import ValidationError
from ..numeric import Number, interpolate, require_non_negative, require_range, to_decimal
from ..quantities.base import Quantity
from ..quantities.temperature import Temperature

SEA_LEVEL_MMHG = Decimal(760)

_SOLUBILITY: dict[int, str] = {
    0: "14.62",
    1: "14.22",
    2: "13.83",
    3: "13.46",
    4: "13.11",
    5: "12.77",
    6: "12.45",
    7: "12.14",
    8: "11.84",
    9: "11.56",
    10: "11.29",
    11: "11.03",
    12: "10.78",
    13: "10.54",
    14: "10.31",
    15: "10.08",
    16: "9.87",
    17: "9.66",
    18: "9.47",
    19: "9.28",
    20: "9.09",
    21: "8.92",
    22: "8.74",
    23: "8.58",
    24: "8.42",
    25: "8.26",
    26: "8.11",
    27: "7.97",
    28: "7.83",
    29: "7.69",
    30: "7.56",
}


def barometric_pressure(elevation_m: Number) -> Decimal:
    """Standard atmosphere pressure in mmHg at an elevation in metres."""

    metres = require_range(elevation_m, -500, 6000, field="elevation_m")
    ratio = (1 - 2.25577e-5 * float(metres)) ** 5.25588
    return to_decimal(round(760 * ratio, 4), field="pressure")


def vapour_pressure(temperature: Temperature) -> Decimal:
    """Saturation vapour pressure of water in mmHg at a temperature.

    It is small, a couple of percent of an atmosphere at rearing temperatures,
    and it is the difference between a saturation figure that agrees with a
    meter and one that is quietly two tenths high.
    """

    celsius = float(temperature.celsius)
    if celsius < -5 or celsius > 60:
        raise ValidationError(
            f"{celsius} degC is outside the vapour pressure fit", field="temperature"
        )
    kelvin = celsius + 273.15
    atmospheres = math.exp(11.8571 - 3840.70 / kelvin - 216961 / (kelvin * kelvin))
    return to_decimal(round(atmospheres * 760, 6), field="pressure")


def solubility_at(temperature: Temperature) -> Decimal:
    """Oxygen a fresh water holds at saturation and 760 mmHg, in mg/L."""

    celsius = temperature.celsius
    if celsius < 0 or celsius > 30:
        raise ValidationError(
            f"{celsius} degC is outside the solubility table", field="temperature"
        )
    low = int(celsius)
    if Decimal(low) == celsius:
        return Decimal(_SOLUBILITY[low])
    return interpolate(
        celsius, low, Decimal(_SOLUBILITY[low]), low + 1, Decimal(_SOLUBILITY[low + 1])
    )


def saturation_concentration(
    temperature: Temperature,
    *,
    elevation_m: Number = 0,
    pressure_mmHg: Number | None = None,
) -> Decimal:
    """Saturation in mg/L at a station's altitude.

    Pass a measured barometer reading if there is one, otherwise the elevation
    stands in for it through the standard atmosphere.
    """

    pressure = (
        to_decimal(pressure_mmHg, field="pressure")
        if pressure_mmHg is not None
        else barometric_pressure(elevation_m)
    )
    if pressure <= 0:
        raise ValidationError("barometric pressure must be positive", field="pressure")
    vapour = vapour_pressure(temperature)
    if pressure <= vapour:
        raise ValidationError("barometric pressure is below the vapour pressure", field="pressure")
    correction = (pressure - vapour) / (SEA_LEVEL_MMHG - vapour)
    return solubility_at(temperature) * correction


def percent_saturation(
    measured_mgL: Number,
    temperature: Temperature,
    *,
    elevation_m: Number = 0,
    pressure_mmHg: Number | None = None,
) -> Decimal:
    """A meter reading as a percentage of what the water could hold."""

    measured = require_non_negative(measured_mgL, field="dissolved_oxygen")
    ceiling = saturation_concentration(
        temperature, elevation_m=elevation_m, pressure_mmHg=pressure_mmHg
    )
    return measured / ceiling * Decimal(100)


def oxygen_deficit(
    measured_mgL: Number,
    temperature: Temperature,
    *,
    elevation_m: Number = 0,
) -> Decimal:
    """How far below saturation a reading sits, in mg/L, never below zero."""

    measured = require_non_negative(measured_mgL, field="dissolved_oxygen")
    ceiling = saturation_concentration(temperature, elevation_m=elevation_m)
    deficit = ceiling - measured
    return deficit if deficit > 0 else Decimal(0)


def available_oxygen(
    flow: Quantity,
    inflow_mgL: Number,
    floor_mgL: Number,
) -> Quantity:
    """Oxygen a flow can give up per hour before it hits the station's floor.

    Returned in kilograms per hour dressed as a mass, because that is the form
    the loading rules want it in.
    """

    inflow = require_non_negative(inflow_mgL, field="inflow")
    floor = require_non_negative(floor_mgL, field="floor")
    if floor > inflow:
        raise ValidationError("the floor is above the inflow reading", field="floor")
    litres_per_hour = flow.to("Lpm").amount * Decimal(60)
    milligrams = litres_per_hour * (inflow - floor)
    return Quantity(milligrams / Decimal(1_000_000), "kg")
