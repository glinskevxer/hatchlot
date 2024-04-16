"""Water temperature, and the interval trap that comes with it.

A point on a temperature scale and a difference between two points are not the
same kind of number, and treating them as one is how a Fahrenheit station ends
up reporting a 5 degree rise as a 41 degree rise. So a temperature subtracted
from a temperature gives a :class:`TemperatureSpan`, which converts by ratio
and has no offset, and a span added to a temperature gives a temperature.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import overload

from ..errors import ValidationError
from ..numeric import Number, quantize, to_decimal
from ..units import System, convert

_ABSOLUTE_ZERO_C = Decimal("-273.15")
_SCALES = {"C", "F"}


def _check_scale(scale: str) -> str:
    if scale not in _SCALES:
        raise ValidationError(f"temperature scale must be C or F, got {scale!r}", field="scale")
    return scale


@dataclass(frozen=True, slots=True, order=False)
class TemperatureSpan:
    """A difference in temperature. Converts by ratio, never by offset."""

    degrees: Decimal
    scale: str

    def __init__(self, degrees: Number, scale: str = "C") -> None:
        object.__setattr__(self, "degrees", to_decimal(degrees, field="degrees"))
        object.__setattr__(self, "scale", _check_scale(scale))

    def to(self, scale: str) -> TemperatureSpan:
        _check_scale(scale)
        if scale == self.scale:
            return self
        ratio = Decimal("1.8") if scale == "F" else Decimal(1) / Decimal("1.8")
        return TemperatureSpan(self.degrees * ratio, scale)

    def __add__(self, other: TemperatureSpan) -> TemperatureSpan:
        return TemperatureSpan(self.degrees + other.to(self.scale).degrees, self.scale)

    def __sub__(self, other: TemperatureSpan) -> TemperatureSpan:
        return TemperatureSpan(self.degrees - other.to(self.scale).degrees, self.scale)

    def __mul__(self, factor: Number) -> TemperatureSpan:
        return TemperatureSpan(self.degrees * to_decimal(factor, field="factor"), self.scale)

    def __neg__(self) -> TemperatureSpan:
        return TemperatureSpan(-self.degrees, self.scale)

    def __abs__(self) -> TemperatureSpan:
        return TemperatureSpan(abs(self.degrees), self.scale)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, TemperatureSpan):
            return NotImplemented
        return self.degrees == other.to(self.scale).degrees

    def __hash__(self) -> int:
        return hash(("span", self.to("C").degrees))

    def __lt__(self, other: TemperatureSpan) -> bool:
        return self.degrees < other.to(self.scale).degrees

    def __le__(self, other: TemperatureSpan) -> bool:
        return self.degrees <= other.to(self.scale).degrees

    def __gt__(self, other: TemperatureSpan) -> bool:
        return self.degrees > other.to(self.scale).degrees

    def __ge__(self, other: TemperatureSpan) -> bool:
        return self.degrees >= other.to(self.scale).degrees

    def __str__(self) -> str:
        return f"{self.degrees.normalize():f} deg{self.scale}"


@dataclass(frozen=True, slots=True, order=False)
class Temperature:
    """A point on a temperature scale, refused below absolute zero."""

    value: Decimal
    scale: str

    def __init__(self, value: Number, scale: str = "C") -> None:
        _check_scale(scale)
        number = to_decimal(value, field="temperature")
        celsius = number if scale == "C" else convert(number, "F", "C")
        if celsius < _ABSOLUTE_ZERO_C:
            raise ValidationError(
                f"{number} deg{scale} is below absolute zero", field="temperature"
            )
        object.__setattr__(self, "value", number)
        object.__setattr__(self, "scale", scale)

    @property
    def celsius(self) -> Decimal:
        return self.value if self.scale == "C" else convert(self.value, "F", "C")

    @property
    def fahrenheit(self) -> Decimal:
        return self.value if self.scale == "F" else convert(self.value, "C", "F")

    def to(self, scale: str) -> Temperature:
        _check_scale(scale)
        if scale == self.scale:
            return self
        return Temperature(self.fahrenheit if scale == "F" else self.celsius, scale)

    def in_system(self, system: System) -> Temperature:
        return self.to("F" if system is System.US else "C")

    def rounded(self, places: int = 1) -> Temperature:
        return Temperature(quantize(self.value, places, field="temperature"), self.scale)

    @overload
    def __sub__(self, other: TemperatureSpan) -> Temperature: ...

    @overload
    def __sub__(self, other: Temperature) -> TemperatureSpan: ...

    def __sub__(self, other: Temperature | TemperatureSpan) -> Temperature | TemperatureSpan:
        if isinstance(other, TemperatureSpan):
            return Temperature(self.value - other.to(self.scale).degrees, self.scale)
        return TemperatureSpan(self.value - other.to(self.scale).value, self.scale)

    def __add__(self, span: TemperatureSpan) -> Temperature:
        return Temperature(self.value + span.to(self.scale).degrees, self.scale)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Temperature):
            return NotImplemented
        return self.celsius == other.celsius

    def __hash__(self) -> int:
        return hash(("temperature", self.celsius))

    def __lt__(self, other: Temperature) -> bool:
        return self.celsius < other.celsius

    def __le__(self, other: Temperature) -> bool:
        return self.celsius <= other.celsius

    def __gt__(self, other: Temperature) -> bool:
        return self.celsius > other.celsius

    def __ge__(self, other: Temperature) -> bool:
        return self.celsius >= other.celsius

    def __str__(self) -> str:
        return f"{self.value.normalize():f} deg{self.scale}"

    @classmethod
    def parse(cls, text: str) -> Temperature:
        """Read `"52.3 F"` or `"11.5C"`."""

        cleaned = text.strip().replace("deg", "").replace("°", " ")
        if not cleaned:
            raise ValidationError("empty temperature", field="temperature")
        scale = cleaned[-1].upper()
        if scale in _SCALES:
            return cls(cleaned[:-1].strip(), scale)
        raise ValidationError(f"no scale on {text!r}", field="temperature")


def mean_temperature(readings: list[Temperature], scale: str = "C") -> Temperature:
    """The average of a set of readings, taken on one scale."""

    if not readings:
        raise ValidationError("cannot average an empty set of readings", field="readings")
    _check_scale(scale)
    total = sum((r.to(scale).value for r in readings), Decimal(0))
    return Temperature(total / Decimal(len(readings)), scale)


def span_between(low: Temperature, high: Temperature, scale: str = "C") -> TemperatureSpan:
    """The positive distance between two readings."""

    return abs(high.to(scale) - low.to(scale))
