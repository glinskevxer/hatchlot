"""Units, and the two systems a station can be run in.

A hatchery is a metric science operated in whatever units the state agency
prints its forms in. The same raceway is 30 feet long on the drawing, holds
4,300 litres in the design file and is loaded in pounds per cubic foot per inch
of fish. So the package keeps one internal base unit per dimension and converts
at the edges, and every display goes through a station's chosen system.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum

from .errors import ConversionError, UnitError
from .numeric import Number, to_decimal


class Dimension(Enum):
    """What a unit measures. Two units only convert inside one dimension."""

    LENGTH = "length"
    MASS = "mass"
    VOLUME = "volume"
    FLOW = "flow"
    TEMPERATURE = "temperature"
    CONCENTRATION = "concentration"
    PRESSURE = "pressure"


class System(Enum):
    """The unit system a station reports in."""

    US = "us"
    METRIC = "metric"


@dataclass(frozen=True, slots=True)
class Unit:
    """One unit: what it measures, how it prints, and its size in base units.

    Temperature is the exception and carries an offset as well as a factor,
    which is why nothing here is a bare multiplication at the call site.
    """

    symbol: str
    dimension: Dimension
    factor: Decimal
    offset: Decimal = Decimal(0)
    system: System | None = None

    def to_base(self, value: Number) -> Decimal:
        return (to_decimal(value, field=self.symbol) + self.offset) * self.factor

    def from_base(self, value: Number) -> Decimal:
        return to_decimal(value, field=self.symbol) / self.factor - self.offset


def _u(
    symbol: str,
    dimension: Dimension,
    factor: str,
    offset: str = "0",
    system: System | None = None,
) -> Unit:
    return Unit(symbol, dimension, Decimal(factor), Decimal(offset), system)


# Base units: metre, kilogram, litre, litre per minute, degree Celsius,
# milligram per litre, millimetre of mercury.
_UNITS: dict[str, Unit] = {
    u.symbol: u
    for u in (
        _u("m", Dimension.LENGTH, "1", system=System.METRIC),
        _u("cm", Dimension.LENGTH, "0.01", system=System.METRIC),
        _u("mm", Dimension.LENGTH, "0.001", system=System.METRIC),
        _u("in", Dimension.LENGTH, "0.0254", system=System.US),
        _u("ft", Dimension.LENGTH, "0.3048", system=System.US),
        _u("kg", Dimension.MASS, "1", system=System.METRIC),
        _u("g", Dimension.MASS, "0.001", system=System.METRIC),
        _u("lb", Dimension.MASS, "0.45359237", system=System.US),
        _u("oz", Dimension.MASS, "0.028349523125", system=System.US),
        _u("L", Dimension.VOLUME, "1", system=System.METRIC),
        _u("m3", Dimension.VOLUME, "1000", system=System.METRIC),
        _u("ft3", Dimension.VOLUME, "28.316846592", system=System.US),
        _u("gal", Dimension.VOLUME, "3.785411784", system=System.US),
        _u("Lpm", Dimension.FLOW, "1", system=System.METRIC),
        _u("m3ph", Dimension.FLOW, "16.6666666666666667", system=System.METRIC),
        _u("gpm", Dimension.FLOW, "3.785411784", system=System.US),
        _u("cfs", Dimension.FLOW, "1699.0107955", system=System.US),
        _u("C", Dimension.TEMPERATURE, "1", system=System.METRIC),
        _u("F", Dimension.TEMPERATURE, "0.55555555555555555556", "-32", system=System.US),
        _u("mgL", Dimension.CONCENTRATION, "1"),
        _u("ugL", Dimension.CONCENTRATION, "0.001"),
        _u("ppm", Dimension.CONCENTRATION, "1"),
        _u("mmHg", Dimension.PRESSURE, "1"),
        _u("kPa", Dimension.PRESSURE, "7.50061682704"),
        _u("atm", Dimension.PRESSURE, "760"),
    )
}


def unit(symbol: str) -> Unit:
    """Look a unit up by symbol, refusing anything the package does not know."""

    try:
        return _UNITS[symbol]
    except KeyError:
        raise UnitError(f"unknown unit {symbol!r}", field="unit") from None


def known_units(dimension: Dimension | None = None) -> tuple[str, ...]:
    """Every symbol, optionally narrowed to one dimension, in a stable order."""

    symbols = [s for s, u in _UNITS.items() if dimension is None or u.dimension is dimension]
    return tuple(sorted(symbols))


def convert(value: Number, source: str, target: str) -> Decimal:
    """Convert between two units of the same dimension.

    Crossing dimensions is a :class:`ConversionError`, not a unit error: both
    units are real, the question is not.
    """

    src = unit(source)
    dst = unit(target)
    if src.dimension is not dst.dimension:
        raise ConversionError(
            f"cannot convert {src.symbol} ({src.dimension.value}) "
            f"to {dst.symbol} ({dst.dimension.value})"
        )
    if src is dst:
        return to_decimal(value, field=source)
    return dst.from_base(src.to_base(value))


def preferred(dimension: Dimension, system: System) -> str:
    """The unit a station in `system` reports `dimension` in."""

    table: dict[tuple[Dimension, System], str] = {
        (Dimension.LENGTH, System.US): "in",
        (Dimension.LENGTH, System.METRIC): "mm",
        (Dimension.MASS, System.US): "lb",
        (Dimension.MASS, System.METRIC): "kg",
        (Dimension.VOLUME, System.US): "ft3",
        (Dimension.VOLUME, System.METRIC): "m3",
        (Dimension.FLOW, System.US): "gpm",
        (Dimension.FLOW, System.METRIC): "Lpm",
        (Dimension.TEMPERATURE, System.US): "F",
        (Dimension.TEMPERATURE, System.METRIC): "C",
        (Dimension.CONCENTRATION, System.US): "mgL",
        (Dimension.CONCENTRATION, System.METRIC): "mgL",
        (Dimension.PRESSURE, System.US): "mmHg",
        (Dimension.PRESSURE, System.METRIC): "kPa",
    }
    return table[(dimension, system)]
