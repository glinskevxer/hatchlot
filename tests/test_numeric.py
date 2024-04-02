from decimal import Decimal

import pytest

from hatchlot.errors import ValidationError
from hatchlot.numeric import (
    clamp,
    interpolate,
    percent_difference,
    quantize,
    require_non_negative,
    require_positive,
    require_range,
    safe_divide,
    to_decimal,
)


def test_float_keeps_the_decimal_form_an_operator_typed():
    assert to_decimal(0.1) == Decimal("0.1")
    assert str(to_decimal(2.675)) == "2.675"


def test_strings_are_stripped_and_thousands_separators_allowed():
    assert to_decimal(" 1,250.5 ") == Decimal("1250.5")


def test_booleans_are_not_quantities():
    with pytest.raises(ValidationError) as excinfo:
        to_decimal(True, field="count")
    assert "count" in str(excinfo.value)


@pytest.mark.parametrize("bad", ["", "  ", "abc", "1.2.3", None, object()])
def test_junk_is_refused(bad):
    with pytest.raises(ValidationError):
        to_decimal(bad)


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), float("-inf")])
def test_non_finite_floats_are_refused(bad):
    with pytest.raises(ValidationError):
        to_decimal(bad)


def test_decimal_nan_is_refused_even_though_it_is_a_decimal():
    with pytest.raises(ValidationError):
        to_decimal(Decimal("NaN"))


def test_quantize_rounds_half_up_not_to_even():
    assert quantize("2.5", 0) == Decimal("3")
    assert quantize("3.5", 0) == Decimal("4")
    assert quantize("0.125", 2) == Decimal("0.13")


def test_quantize_refuses_negative_places():
    with pytest.raises(ValidationError):
        quantize("1.0", -1)


def test_require_positive_and_non_negative_draw_the_line_in_different_places():
    assert require_positive("0.001", field="flow") == Decimal("0.001")
    assert require_non_negative(0, field="mort") == Decimal("0")
    with pytest.raises(ValidationError):
        require_positive(0, field="flow")
    with pytest.raises(ValidationError):
        require_non_negative("-0.5", field="mort")


def test_require_range_is_closed_at_both_ends():
    assert require_range(5, 5, 10, field="ph") == Decimal("5")
    assert require_range(10, 5, 10, field="ph") == Decimal("10")
    with pytest.raises(ValidationError):
        require_range("10.01", 5, 10, field="ph")


def test_require_range_refuses_an_inverted_range():
    with pytest.raises(ValidationError):
        require_range(5, 10, 1, field="ph")


def test_safe_divide_names_the_field_instead_of_raising_division_by_zero():
    assert safe_divide(10, 4, field="fpp") == Decimal("2.5")
    with pytest.raises(ValidationError) as excinfo:
        safe_divide(10, 0, field="fpp")
    assert "fpp" in str(excinfo.value)


def test_clamp_pulls_inside_rather_than_refusing():
    assert clamp("-3", 0, 100) == Decimal("0")
    assert clamp("133", 0, 100) == Decimal("100")
    assert clamp("42", 0, 100) == Decimal("42")
    with pytest.raises(ValidationError):
        clamp(1, 10, 0)


def test_percent_difference_is_signed_and_relative_to_expected():
    assert percent_difference(110, 100) == Decimal("10")
    assert percent_difference(90, 100) == Decimal("-10")
    with pytest.raises(ValidationError):
        percent_difference(1, 0)


def test_percent_difference_uses_the_magnitude_of_a_negative_expected():
    assert percent_difference(-5, -10) == Decimal("50")


def test_interpolate_hits_both_endpoints_and_the_middle():
    assert interpolate(4, 0, 0, 8, 100) == Decimal("50")
    assert interpolate(0, 0, 12, 8, 100) == Decimal("12")
    assert interpolate(8, 0, 12, 8, 100) == Decimal("100")


def test_interpolate_extrapolates_rather_than_clamping():
    assert interpolate(10, 0, 0, 5, 10) == Decimal("20")


def test_interpolate_refuses_a_degenerate_interval():
    with pytest.raises(ValidationError):
        interpolate(1, 2, 3, 2, 9)
