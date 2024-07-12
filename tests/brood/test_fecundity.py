from decimal import Decimal

import pytest

from hatchlot.brood.fecundity import (
    DEFAULT_MODEL,
    FecundityModel,
    Observation,
    females_needed,
    fit,
    residual_spread,
)
from hatchlot.errors import ValidationError
from hatchlot.quantities.base import Quantity


def test_the_default_model_puts_a_chinook_hen_in_the_right_range():
    eggs = DEFAULT_MODEL.expected(Quantity(78, "cm"))
    assert Decimal(4000) < eggs < Decimal(8000)


def test_a_bigger_female_carries_more():
    small = DEFAULT_MODEL.expected(Quantity(60, "cm"))
    big = DEFAULT_MODEL.expected(Quantity(90, "cm"))
    assert big > small * Decimal(2)


def test_a_model_with_impossible_coefficients_is_refused():
    with pytest.raises(ValidationError):
        FecundityModel(scale=Decimal(0), exponent=Decimal(3))
    with pytest.raises(ValidationError):
        FecundityModel(scale=Decimal(1), exponent=Decimal(0))
    with pytest.raises(ValidationError):
        FecundityModel(scale=Decimal(1), exponent=Decimal(3), sample_size=-1)


def test_a_female_of_no_length_is_refused():
    with pytest.raises(ValidationError):
        DEFAULT_MODEL.expected(Quantity(0, "cm"))


def test_a_pen_is_the_sum_of_its_females():
    lengths = [Quantity(70, "cm"), Quantity(80, "cm")]
    expected = DEFAULT_MODEL.expected_total(lengths)
    assert expected == DEFAULT_MODEL.expected(lengths[0]) + DEFAULT_MODEL.expected(lengths[1])
    assert DEFAULT_MODEL.expected_total([]) == Decimal(0)


def test_the_deviation_is_signed_against_the_model():
    length = Quantity(78, "cm")
    expected = DEFAULT_MODEL.expected(length)
    assert DEFAULT_MODEL.deviation(length, expected) == Decimal(0)
    assert DEFAULT_MODEL.deviation(length, expected * Decimal("1.1")) > 0
    assert DEFAULT_MODEL.deviation(length, expected * Decimal("0.9")) < 0


def test_a_count_of_nothing_is_not_a_deviation():
    with pytest.raises(ValidationError):
        DEFAULT_MODEL.deviation(Quantity(78, "cm"), 0)


def test_plausibility_is_a_band_around_the_model():
    length = Quantity(78, "cm")
    expected = DEFAULT_MODEL.expected(length)
    assert DEFAULT_MODEL.is_plausible(length, expected * Decimal("1.3"))
    assert not DEFAULT_MODEL.is_plausible(length, expected * Decimal("1.8"))
    assert DEFAULT_MODEL.is_plausible(length, expected * Decimal("1.8"), tolerance=100)


def test_an_observation_needs_a_real_fish_and_a_real_count():
    with pytest.raises(ValidationError):
        Observation(Quantity(78, "cm"), 0)
    with pytest.raises(ValidationError):
        Observation(Quantity(0, "cm"), 5000)


def observations_from(model, lengths):
    return [
        Observation(Quantity(length, "cm"), model.expected(Quantity(length, "cm")))
        for length in lengths
    ]


def test_a_fit_recovers_the_model_that_generated_the_data():
    fitted = fit(observations_from(DEFAULT_MODEL, [60, 70, 80, 90]))
    assert abs(fitted.exponent - DEFAULT_MODEL.exponent) < Decimal("0.01")
    assert fitted.sample_size == 4


def test_a_fit_from_a_real_looking_scatter_lands_between_the_points():
    observations = [
        Observation(Quantity(66, "cm"), 3400),
        Observation(Quantity(72, "cm"), 4600),
        Observation(Quantity(78, "cm"), 5500),
        Observation(Quantity(84, "cm"), 6900),
    ]
    fitted = fit(observations)
    assert Decimal(2) < fitted.exponent < Decimal(4)
    assert residual_spread(fitted, observations) < Decimal(10)


def test_a_fit_needs_more_than_two_females():
    with pytest.raises(ValidationError):
        fit(observations_from(DEFAULT_MODEL, [70, 80]))


def test_a_fit_of_identical_females_has_no_slope_to_find():
    with pytest.raises(ValidationError):
        fit(observations_from(DEFAULT_MODEL, [70, 70, 70]))


def test_a_fit_that_falls_with_size_is_refused_as_nonsense():
    observations = [
        Observation(Quantity(60, "cm"), 6000),
        Observation(Quantity(70, "cm"), 5000),
        Observation(Quantity(80, "cm"), 4000),
    ]
    with pytest.raises(ValidationError):
        fit(observations)


def test_the_residual_spread_of_a_perfect_fit_is_nothing():
    observations = observations_from(DEFAULT_MODEL, [60, 70, 80, 90])
    assert residual_spread(DEFAULT_MODEL, observations) < Decimal("0.01")


def test_scoring_nothing_is_refused():
    with pytest.raises(ValidationError):
        residual_spread(DEFAULT_MODEL, [])


def test_how_many_females_a_target_take_needs():
    each = DEFAULT_MODEL.expected(Quantity(78, "cm"))
    assert females_needed(DEFAULT_MODEL, each * Decimal(10), Quantity(78, "cm")) == 10


def test_a_partial_female_rounds_up_to_a_whole_one():
    each = DEFAULT_MODEL.expected(Quantity(78, "cm"))
    assert females_needed(DEFAULT_MODEL, each * Decimal("10.1"), Quantity(78, "cm")) == 11


def test_a_target_of_nothing_is_refused():
    with pytest.raises(ValidationError):
        females_needed(DEFAULT_MODEL, 0, Quantity(78, "cm"))
