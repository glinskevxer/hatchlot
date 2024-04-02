"""Number handling the whole package shares.

Hatchery paperwork is full of numbers that came off a scale, a ruler or a
spreadsheet, and every one of them arrives as text at some point. The rules here
are deliberately boring and deliberately in one place: parse once, round once,
and never let a float rounding artefact reach a report.
"""

from __future__ import annotations

import math
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from .errors import ValidationError

Number = int | float | Decimal | str


def to_decimal(value: Number, *, field: str | None = None) -> Decimal:
    """Coerce anything numeric to :class:`~decimal.Decimal`.

    Floats go through `repr` rather than `Decimal(float)` so that 0.1 stays 0.1
    instead of becoming the exact binary value, which no operator would
    recognise on a printout.
    """

    if isinstance(value, Decimal):
        result = value
    elif isinstance(value, bool):
        raise ValidationError("a boolean is not a quantity", field=field)
    elif isinstance(value, int):
        result = Decimal(value)
    elif isinstance(value, float):
        if math.isnan(value) or math.isinf(value):
            raise ValidationError(f"{value!r} is not a finite number", field=field)
        result = Decimal(repr(value))
    elif isinstance(value, str):
        text = value.strip().replace(",", "")
        if not text:
            raise ValidationError("empty string is not a number", field=field)
        try:
            result = Decimal(text)
        except InvalidOperation:
            raise ValidationError(f"{value!r} is not a number", field=field) from None
    else:
        raise ValidationError(f"{type(value).__name__} is not a number", field=field)
    if not result.is_finite():
        raise ValidationError(f"{value!r} is not a finite number", field=field)
    return result


def quantize(value: Number, places: int, *, field: str | None = None) -> Decimal:
    """Round half up to `places` decimal places.

    Half up, not banker's rounding. Every hatchery form this package prints has
    to agree with a number somebody worked out by hand, and by hand nobody
    rounds a half to even.
    """

    if places < 0:
        raise ValidationError("places cannot be negative", field=field)
    exponent = Decimal(1).scaleb(-places)
    return to_decimal(value, field=field).quantize(exponent, rounding=ROUND_HALF_UP)


def require_positive(value: Number, *, field: str) -> Decimal:
    """Return the value as a Decimal, refusing zero and anything below it."""

    number = to_decimal(value, field=field)
    if number <= 0:
        raise ValidationError(f"must be greater than zero, got {number}", field=field)
    return number


def require_non_negative(value: Number, *, field: str) -> Decimal:
    """Return the value as a Decimal, refusing anything below zero."""

    number = to_decimal(value, field=field)
    if number < 0:
        raise ValidationError(f"cannot be negative, got {number}", field=field)
    return number


def require_range(value: Number, low: Number, high: Number, *, field: str) -> Decimal:
    """Return the value as a Decimal, refusing anything outside the closed range."""

    number = to_decimal(value, field=field)
    lo = to_decimal(low, field=field)
    hi = to_decimal(high, field=field)
    if lo > hi:
        raise ValidationError(f"range {lo}..{hi} is inverted", field=field)
    if not lo <= number <= hi:
        raise ValidationError(f"must be between {lo} and {hi}, got {number}", field=field)
    return number


def safe_divide(numerator: Number, denominator: Number, *, field: str) -> Decimal:
    """Divide, refusing a zero denominator rather than raising DivisionByZero."""

    bottom = to_decimal(denominator, field=field)
    if bottom == 0:
        raise ValidationError("division by zero", field=field)
    return to_decimal(numerator, field=field) / bottom


def clamp(value: Number, low: Number, high: Number, *, field: str = "value") -> Decimal:
    """Pull a value inside a range instead of refusing it."""

    number = to_decimal(value, field=field)
    lo = to_decimal(low, field=field)
    hi = to_decimal(high, field=field)
    if lo > hi:
        raise ValidationError(f"range {lo}..{hi} is inverted", field=field)
    return min(max(number, lo), hi)


def percent_difference(observed: Number, expected: Number, *, field: str = "value") -> Decimal:
    """Signed difference of `observed` from `expected`, in percent of expected."""

    base = to_decimal(expected, field=field)
    if base == 0:
        raise ValidationError("cannot take a percent difference from zero", field=field)
    return (to_decimal(observed, field=field) - base) / abs(base) * Decimal(100)


def interpolate(x: Number, x0: Number, y0: Number, x1: Number, y1: Number) -> Decimal:
    """Straight line interpolation between two points.

    Used for calibration curves, oxygen solubility tables and feed tables, all of
    which arrive as sparse rows that have to answer a question between rows.
    """

    xd = to_decimal(x, field="x")
    a = to_decimal(x0, field="x0")
    b = to_decimal(x1, field="x1")
    if a == b:
        raise ValidationError("cannot interpolate between identical abscissae", field="x0")
    fa = to_decimal(y0, field="y0")
    fb = to_decimal(y1, field="y1")
    return fa + (fb - fa) * (xd - a) / (b - a)
