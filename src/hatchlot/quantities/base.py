"""A number with a unit attached.

Bare floats are how a hatchery ends up loading a raceway in the wrong system.
Everything the engine reasons about carries its unit, converts on demand, and
refuses to be added to a different dimension.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from ..errors import ConversionError, ValidationError
from ..numeric import Number, quantize, to_decimal
from ..units import Dimension, System, convert, unit


@dataclass(frozen=True, slots=True, order=False)
class Quantity:
    """An amount in a named unit.

    Comparison and arithmetic convert the right hand side into the left hand
    unit first, so the unit of a result is always the unit of the left operand.
    That rule is arbitrary but it is written down, which is the point.
    """

    amount: Decimal
    symbol: str

    def __init__(self, amount: Number, symbol: str) -> None:
        u = unit(symbol)
        object.__setattr__(self, "amount", to_decimal(amount, field=symbol))
        object.__setattr__(self, "symbol", u.symbol)

    @property
    def dimension(self) -> Dimension:
        return unit(self.symbol).dimension

    def to(self, symbol: str) -> Quantity:
        """This amount expressed in another unit of the same dimension."""

        return Quantity(convert(self.amount, self.symbol, symbol), symbol)

    def in_system(self, system: System) -> Quantity:
        """This amount in the unit a station running `system` reports in."""

        from ..units import preferred

        return self.to(preferred(self.dimension, system))

    def rounded(self, places: int) -> Quantity:
        return Quantity(quantize(self.amount, places, field=self.symbol), self.symbol)

    def _aligned(self, other: Quantity) -> Decimal:
        if not isinstance(other, Quantity):  # pragma: no cover - guarded by callers
            raise TypeError("expected a Quantity")
        if other.dimension is not self.dimension:
            raise ConversionError(
                f"cannot combine {self.dimension.value} with {other.dimension.value}"
            )
        return convert(other.amount, other.symbol, self.symbol)

    def __add__(self, other: Quantity) -> Quantity:
        return Quantity(self.amount + self._aligned(other), self.symbol)

    def __sub__(self, other: Quantity) -> Quantity:
        return Quantity(self.amount - self._aligned(other), self.symbol)

    def __mul__(self, factor: Number) -> Quantity:
        return Quantity(self.amount * to_decimal(factor, field="factor"), self.symbol)

    def __truediv__(self, divisor: Number) -> Quantity:
        value = to_decimal(divisor, field="divisor")
        if value == 0:
            raise ValidationError("cannot divide a quantity by zero", field="divisor")
        return Quantity(self.amount / value, self.symbol)

    def __neg__(self) -> Quantity:
        return Quantity(-self.amount, self.symbol)

    def __abs__(self) -> Quantity:
        return Quantity(abs(self.amount), self.symbol)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Quantity):
            return NotImplemented
        if other.dimension is not self.dimension:
            return False
        return self.amount == self._aligned(other)

    def __hash__(self) -> int:
        return hash((self.dimension, unit(self.symbol).to_base(self.amount)))

    def __lt__(self, other: Quantity) -> bool:
        return self.amount < self._aligned(other)

    def __le__(self, other: Quantity) -> bool:
        return self.amount <= self._aligned(other)

    def __gt__(self, other: Quantity) -> bool:
        return self.amount > self._aligned(other)

    def __ge__(self, other: Quantity) -> bool:
        return self.amount >= self._aligned(other)

    def __str__(self) -> str:
        return f"{self.amount.normalize():f} {self.symbol}"

    def __repr__(self) -> str:
        return f"Quantity({str(self.amount)!r}, {self.symbol!r})"

    @classmethod
    def parse(cls, text: str) -> Quantity:
        """Read `"12.5 gpm"`, the way it is written on a clipboard."""

        parts = text.strip().split()
        if len(parts) != 2:
            raise ValidationError(f"expected an amount and a unit, got {text!r}", field="quantity")
        return cls(parts[0], parts[1])

    def as_tuple(self) -> tuple[str, str]:
        """A storable form: the amount as text, and the unit."""

        return (str(self.amount), self.symbol)


def sum_quantities(items: list[Quantity], symbol: str) -> Quantity:
    """Total a list into one unit, tolerating an empty list."""

    total = Quantity(0, symbol)
    for item in items:
        total = total + item
    return total


def as_quantity(value: Any, symbol: str) -> Quantity:
    """Accept either a Quantity or a bare number, and end up with a Quantity."""

    if isinstance(value, Quantity):
        return value.to(symbol)
    return Quantity(value, symbol)
