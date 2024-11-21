from decimal import Decimal

import pytest

from hatchlot.errors import ValidationError
from hatchlot.feed.conversion import (
    Conversion,
    combined,
    cost_per_gain,
    feed_needed,
    gain_expected,
)
from hatchlot.numeric import quantize
from hatchlot.quantities.base import Quantity


def period(fed="100", opening="500", closing="580", dead="20"):
    return Conversion(
        fed=Quantity(fed, "kg"),
        opening_biomass=Quantity(opening, "kg"),
        closing_biomass=Quantity(closing, "kg"),
        mortality_biomass=Quantity(dead, "kg"),
    )


def test_the_two_gains_are_not_the_same_number():
    entry = period()
    assert entry.gain == Quantity(80, "kg")
    assert entry.biological_gain == Quantity(100, "kg")


def test_the_biological_ratio_always_looks_better():
    entry = period()
    assert entry.economic_ratio == Decimal("1.25")
    assert entry.biological_ratio == Decimal(1)
    assert entry.biological_ratio < entry.economic_ratio


def test_with_no_mortality_the_two_ratios_are_the_same():
    entry = period(dead="0")
    assert entry.economic_ratio == entry.biological_ratio


def test_a_period_that_lost_weight_has_no_conversion():
    entry = period(opening="500", closing="450", dead="0")
    with pytest.raises(ValidationError):
        assert entry.economic_ratio
    with pytest.raises(ValidationError):
        assert entry.biological_ratio


def test_a_negative_weight_anywhere_is_refused():
    with pytest.raises(ValidationError):
        period(fed="-1")
    with pytest.raises(ValidationError):
        period(dead="-1")


def test_the_efficiency_is_the_ratio_the_other_way_up():
    assert quantize(period().efficiency, 0) == Decimal(80)


def test_a_believable_conversion_and_two_that_are_not():
    assert period().is_plausible()
    assert not period(fed="500").is_plausible()
    assert not period(fed="20").is_plausible()
    assert period(fed="500").is_plausible(ceiling=10)


def test_a_period_with_no_gain_is_not_plausible_rather_than_raising():
    assert not period(closing="450", dead="0").is_plausible()


def test_a_ceiling_of_nothing_is_refused():
    with pytest.raises(ValidationError):
        period().is_plausible(ceiling=0)


def test_the_feed_a_planned_gain_will_take():
    assert feed_needed(Quantity(100, "kg"), "1.2") == Quantity(120, "kg")
    with pytest.raises(ValidationError):
        feed_needed(Quantity(0, "kg"), "1.2")
    with pytest.raises(ValidationError):
        feed_needed(Quantity(100, "kg"), 0)


def test_the_gain_a_quantity_of_feed_should_give():
    assert gain_expected(Quantity(120, "kg"), "1.2") == Quantity(100, "kg")
    with pytest.raises(ValidationError):
        gain_expected(Quantity(120, "kg"), 0)


def test_what_a_kilogram_of_fish_cost_in_feed():
    assert cost_per_gain(Quantity(120, "kg"), "2.00", Quantity(100, "kg")) == Decimal("2.4")
    with pytest.raises(ValidationError):
        cost_per_gain(Quantity(120, "kg"), "-1", Quantity(100, "kg"))
    with pytest.raises(ValidationError):
        cost_per_gain(Quantity(120, "kg"), "2.00", Quantity(0, "kg"))


def test_several_periods_combine_on_the_weights_not_the_ratios():
    first = period(fed="100", opening="500", closing="580", dead="20")
    second = period(fed="200", opening="580", closing="760", dead="20")
    whole = combined([first, second])
    assert whole.fed == Quantity(300, "kg")
    assert whole.opening_biomass == Quantity(500, "kg")
    assert whole.closing_biomass == Quantity(760, "kg")
    assert whole.mortality_biomass == Quantity(40, "kg")
    assert quantize(whole.economic_ratio, 4) == Decimal("1.1538")


def test_the_combined_ratio_is_not_the_mean_of_the_two():
    first = period(fed="100", opening="500", closing="580", dead="20")
    second = period(fed="200", opening="580", closing="760", dead="20")
    mean_of_ratios = (first.economic_ratio + second.economic_ratio) / Decimal(2)
    assert combined([first, second]).economic_ratio != mean_of_ratios


def test_combining_nothing_is_refused():
    with pytest.raises(ValidationError):
        combined([])
