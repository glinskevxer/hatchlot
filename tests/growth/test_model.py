from decimal import Decimal

import pytest

from hatchlot.errors import ValidationError
from hatchlot.growth.model import (
    GrowthModel,
    condition_length,
    cube_root,
    fit_coefficient,
    specific_growth_rate,
    weight_after_days,
)
from hatchlot.numeric import quantize
from hatchlot.quantities.base import Quantity

MODEL = GrowthModel(coefficient=Decimal("2.0"))


def test_the_cube_root_of_a_cube():
    assert quantize(cube_root(27), 6) == Decimal("27.000000") ** 0 * Decimal(3)
    with pytest.raises(ValidationError):
        cube_root(0)


def test_a_model_needs_a_real_coefficient():
    with pytest.raises(ValidationError):
        GrowthModel(coefficient=Decimal(0))
    with pytest.raises(ValidationError):
        GrowthModel(coefficient=Decimal(2), fitted_on_days=-1)


def test_a_lot_grows_on_thermal_units():
    grown = MODEL.grow(Quantity(1, "g"), 1000)
    assert grown > Quantity(1, "g")
    assert quantize(grown.to("g").amount, 2) == Decimal("27.00")


def test_no_thermal_units_means_no_growth():
    assert quantize(MODEL.grow(Quantity(5, "g"), 0).to("g").amount, 6) == Decimal("5.000000")


def test_negative_units_or_a_weightless_fish_are_refused():
    with pytest.raises(ValidationError):
        MODEL.grow(Quantity(1, "g"), -10)
    with pytest.raises(ValidationError):
        MODEL.grow(Quantity(0, "g"), 100)


def test_the_units_needed_to_reach_a_size():
    units = MODEL.units_to_reach(Quantity(1, "g"), Quantity(27, "g"))
    assert quantize(units, 2) == Decimal("1000.00")


def test_a_target_no_bigger_than_the_start_is_not_a_question():
    with pytest.raises(ValidationError):
        MODEL.units_to_reach(Quantity(10, "g"), Quantity(10, "g"))
    with pytest.raises(ValidationError):
        MODEL.units_to_reach(Quantity(10, "g"), Quantity(5, "g"))


def test_the_days_to_reach_a_size_on_a_steady_water():
    assert MODEL.days_to_reach(Quantity(1, "g"), Quantity(27, "g"), 10) == 100
    assert MODEL.days_to_reach(Quantity(1, "g"), Quantity(27, "g"), 5) == 200


def test_colder_water_takes_longer():
    warm = MODEL.days_to_reach(Quantity(2, "g"), Quantity(20, "g"), 12)
    cold = MODEL.days_to_reach(Quantity(2, "g"), Quantity(20, "g"), 6)
    assert cold > warm
    with pytest.raises(ValidationError):
        MODEL.days_to_reach(Quantity(2, "g"), Quantity(20, "g"), 0)


def test_a_coefficient_fitted_from_a_lot_that_grew():
    fitted = fit_coefficient(Quantity(1, "g"), Quantity(27, "g"), 1000)
    assert quantize(fitted.coefficient, 4) == Decimal("2.0000")


def test_fitting_on_a_lot_that_did_not_grow_is_refused():
    with pytest.raises(ValidationError):
        fit_coefficient(Quantity(10, "g"), Quantity(10, "g"), 1000)
    with pytest.raises(ValidationError):
        fit_coefficient(Quantity(1, "g"), Quantity(10, "g"), 0)


def test_a_fitted_model_reproduces_the_growth_it_was_fitted_on():
    fitted = fit_coefficient(Quantity(2, "g"), Quantity(15, "g"), 800)
    grown = fitted.grow(Quantity(2, "g"), 800)
    assert quantize(grown.to("g").amount, 2) == Decimal("15.00")


def test_the_specific_growth_rate_is_a_percent_a_day():
    rate = specific_growth_rate(Quantity(1, "g"), Quantity(2, "g"), 10)
    assert quantize(rate, 2) == Decimal("7.18")


def test_the_specific_rate_falls_as_the_fish_grow_which_is_the_point():
    model = GrowthModel(coefficient=Decimal(2))
    early = specific_growth_rate(Quantity(1, "g"), model.grow(Quantity(1, "g"), 300), 30)
    late = specific_growth_rate(Quantity(50, "g"), model.grow(Quantity(50, "g"), 300), 30)
    assert late < early


def test_a_growth_rate_over_no_days_is_refused():
    with pytest.raises(ValidationError):
        specific_growth_rate(Quantity(1, "g"), Quantity(2, "g"), 0)


def test_where_a_lot_gets_to_in_a_number_of_days():
    grown = weight_after_days(MODEL, Quantity(1, "g"), 10, 100)
    assert quantize(grown.to("g").amount, 2) == Decimal("27.00")
    held = weight_after_days(MODEL, Quantity(5, "g"), 10, 0)
    assert quantize(held.to("g").amount, 6) == Decimal("5.000000")


def test_growing_backwards_or_on_no_water_is_refused():
    with pytest.raises(ValidationError):
        weight_after_days(MODEL, Quantity(1, "g"), 10, -1)
    with pytest.raises(ValidationError):
        weight_after_days(MODEL, Quantity(1, "g"), 0, 10)


def test_the_length_a_weight_comes_to():
    length = condition_length(Quantity("2.5", "g"), "0.0004")
    assert quantize(length.to("in").amount, 2) == Decimal("2.40")
    with pytest.raises(ValidationError):
        condition_length(Quantity(0, "g"), "0.0004")
    with pytest.raises(ValidationError):
        condition_length(Quantity(1, "g"), 0)
