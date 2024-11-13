from decimal import Decimal

import pytest

from hatchlot.errors import ValidationError
from hatchlot.feed.ration import (
    daily_ration,
    feeding_rate,
    feeds_per_day,
    per_feeding,
    plan_ration,
    ration_for,
)
from hatchlot.numeric import quantize
from hatchlot.quantities.base import Quantity
from hatchlot.quantities.temperature import Temperature


def test_a_cell_of_the_chart_is_read_straight():
    assert feeding_rate(Quantity(1, "g"), Temperature(10, "C")) == Decimal("4.3")
    assert feeding_rate(Quantity(30, "g"), Temperature(4, "C")) == Decimal("0.8")


def test_small_fish_eat_a_bigger_share_of_themselves():
    warm = Temperature(10, "C")
    assert feeding_rate(Quantity(1, "g"), warm) > feeding_rate(Quantity(30, "g"), warm)


def test_warm_water_puts_the_rate_up():
    fish = Quantity(3, "g")
    assert feeding_rate(fish, Temperature(16, "C")) > feeding_rate(fish, Temperature(4, "C"))


def test_between_two_rows_the_chart_interpolates():
    between = feeding_rate(Quantity(2, "g"), Temperature(10, "C"))
    assert Decimal("3.0") < between < Decimal("4.3")


def test_between_two_columns_it_interpolates_as_well():
    between = feeding_rate(Quantity(1, "g"), Temperature("8.5", "C"))
    assert Decimal("3.3") < between < Decimal("4.3")


def test_off_the_ends_of_the_chart_it_clamps_rather_than_extrapolating():
    assert feeding_rate(Quantity("0.1", "g"), Temperature(10, "C")) == Decimal("6.0")
    assert feeding_rate(Quantity(500, "g"), Temperature(10, "C")) == Decimal("0.9")
    assert feeding_rate(Quantity(1, "g"), Temperature(1, "C")) == Decimal("2.4")
    assert feeding_rate(Quantity(1, "g"), Temperature(20, "C")) == Decimal("5.6")


def test_a_fish_of_no_weight_is_refused():
    with pytest.raises(ValidationError):
        feeding_rate(Quantity(0, "g"), Temperature(10, "C"))


def test_a_fahrenheit_reading_finds_the_same_cell():
    assert feeding_rate(Quantity(1, "g"), Temperature(50, "F")) == Decimal("4.3")


def test_the_ration_is_the_rate_against_the_biomass():
    assert daily_ration(Quantity(1000, "kg"), 3) == Quantity(30, "kg")
    assert daily_ration(Quantity(0, "kg"), 3) == Quantity(0, "kg")
    assert daily_ration(Quantity(1000, "kg"), 0) == Quantity(0, "kg")


def test_a_negative_rate_or_biomass_is_refused():
    with pytest.raises(ValidationError):
        daily_ration(Quantity(1000, "kg"), -1)
    with pytest.raises(ValidationError):
        daily_ration(Quantity(-1, "kg"), 3)


def test_the_ration_for_a_lot_goes_through_the_chart():
    ration = ration_for(Quantity(1000, "kg"), Quantity(1, "g"), Temperature(10, "C"))
    assert ration == Quantity(43, "kg")


def test_how_often_fish_of_a_size_are_fed():
    assert feeds_per_day(Quantity("0.5", "g")) == 8
    assert feeds_per_day(Quantity(3, "g")) == 6
    assert feeds_per_day(Quantity(10, "g")) == 4
    assert feeds_per_day(Quantity(30, "g")) == 3
    assert feeds_per_day(Quantity(100, "g")) == 2


def test_a_fish_of_no_weight_gets_no_feeding_schedule():
    with pytest.raises(ValidationError):
        feeds_per_day(Quantity(0, "g"))


def test_the_ration_splits_across_the_day():
    assert per_feeding(Quantity(24, "kg"), Quantity(10, "g")) == Quantity(6, "kg")


def test_a_plan_covers_a_stretch_of_days():
    plan = plan_ration(
        "2024-CHK-01", Quantity(1000, "kg"), Quantity(1, "g"), Temperature(10, "C"), 7
    )
    assert plan.rate_percent == Decimal("4.3")
    assert plan.daily == Quantity(43, "kg")
    assert plan.total == Quantity(301, "kg")
    assert plan.feedings == 6
    assert quantize(plan.per_feeding.to("kg").amount, 3) == Decimal("7.167")


def test_a_plan_of_no_days_is_refused():
    with pytest.raises(ValidationError):
        plan_ration("2024-CHK-01", Quantity(1000, "kg"), Quantity(1, "g"), Temperature(10, "C"), 0)
