from datetime import date
from decimal import Decimal

import pytest

from hatchlot.calendar import DateRange
from hatchlot.errors import ValidationError
from hatchlot.quantities.temperature import Temperature
from hatchlot.water.thermal import DailyTemperature, GapPolicy, ThermalSeries


def series(pairs):
    built = ThermalSeries()
    for day, value in pairs:
        built.add(day, value)
    return built


def steady(start, days, celsius="10"):
    built = ThermalSeries()
    for offset in range(days):
        built.add(date.fromordinal(date.fromisoformat(start).toordinal() + offset), celsius)
    return built


def test_a_reading_takes_a_temperature_object_or_a_number():
    assert DailyTemperature("2024-09-01", Temperature(50, "F")).celsius == Decimal(10)
    assert DailyTemperature("2024-09-01", "10").celsius == Decimal(10)
    assert DailyTemperature("2024-09-01", 10).temperature == Temperature(10, "C")


def test_readings_sort_by_day():
    readings = [DailyTemperature("2024-09-02", 9), DailyTemperature("2024-09-01", 10)]
    assert [r.day for r in sorted(readings)][0] == date(2024, 9, 1)


def test_a_series_iterates_in_day_order_whatever_order_it_was_written_in():
    built = series([("2024-09-03", 9), ("2024-09-01", 11), ("2024-09-02", 10)])
    assert [r.celsius for r in built] == [Decimal(11), Decimal(10), Decimal(9)]
    assert len(built) == 3


def test_writing_a_day_twice_keeps_the_last_value():
    built = series([("2024-09-01", 11), ("2024-09-01", 12)])
    assert built.get("2024-09-01") == Decimal(12)
    assert len(built) == 1


def test_an_empty_series_covers_nothing():
    assert ThermalSeries().covered is None
    assert ThermalSeries().get("2024-09-01") is None


def test_the_covered_range_is_the_ends_not_a_promise_of_completeness():
    built = series([("2024-09-01", 10), ("2024-09-05", 10)])
    assert built.covered == DateRange("2024-09-01", "2024-09-05")
    assert built.missing_days(DateRange("2024-09-01", "2024-09-05")) == (
        date(2024, 9, 2),
        date(2024, 9, 3),
        date(2024, 9, 4),
    )
    assert "2024-09-01" in built
    assert "2024-09-02" not in built


def test_units_are_the_sum_of_the_daily_means():
    built = steady("2024-09-01", 10, "10")
    assert built.accumulate(DateRange("2024-09-01", "2024-09-10")) == Decimal(100)


def test_a_zero_point_is_subtracted_from_every_day():
    built = steady("2024-09-01", 10, "10")
    assert built.accumulate(DateRange("2024-09-01", "2024-09-10"), zero_point_c=4) == Decimal(60)


def test_a_day_below_the_zero_point_contributes_nothing_not_a_negative():
    built = series([("2024-09-01", 2), ("2024-09-02", 10)])
    assert built.accumulate(DateRange("2024-09-01", "2024-09-02"), zero_point_c=5) == Decimal(5)


def test_a_missing_day_refuses_by_default():
    built = series([("2024-09-01", 10), ("2024-09-03", 10)])
    with pytest.raises(ValidationError):
        built.accumulate(DateRange("2024-09-01", "2024-09-03"))


def test_carry_forward_uses_the_last_reading_before_the_hole():
    built = series([("2024-09-01", 10), ("2024-09-03", 20)])
    total = built.accumulate(DateRange("2024-09-01", "2024-09-03"), policy=GapPolicy.CARRY_FORWARD)
    assert total == Decimal(40)


def test_interpolation_walks_across_the_hole():
    built = series([("2024-09-01", 10), ("2024-09-03", 20)])
    total = built.accumulate(DateRange("2024-09-01", "2024-09-03"), policy=GapPolicy.INTERPOLATE)
    assert total == Decimal(45)


def test_interpolation_falls_back_to_carrying_forward_past_the_last_reading():
    built = series([("2024-09-01", 10), ("2024-09-02", 20)])
    total = built.accumulate(DateRange("2024-09-01", "2024-09-04"), policy=GapPolicy.INTERPOLATE)
    assert total == Decimal(70)


def test_nothing_before_a_hole_cannot_be_filled_by_any_policy():
    built = series([("2024-09-05", 10)])
    with pytest.raises(ValidationError):
        built.accumulate(DateRange("2024-09-01", "2024-09-05"), policy=GapPolicy.CARRY_FORWARD)


def test_the_mean_over_a_window_is_a_temperature():
    built = series([("2024-09-01", 10), ("2024-09-02", 12)])
    assert built.mean(DateRange("2024-09-01", "2024-09-02")) == Temperature(11, "C")


def test_the_day_a_lot_reaches_its_target():
    built = steady("2024-09-01", 100, "10")
    assert built.day_units_reach("2024-09-01", 100) == date(2024, 9, 10)


def test_the_target_lands_on_the_day_the_count_is_first_met():
    built = steady("2024-09-01", 100, "10")
    assert built.day_units_reach("2024-09-01", 95) == date(2024, 9, 10)
    assert built.day_units_reach("2024-09-01", "90") == date(2024, 9, 9)


def test_an_empty_series_answers_nothing_rather_than_raising():
    assert ThermalSeries().day_units_reach("2024-09-01", 100) is None


def test_a_series_that_runs_out_answers_nothing_rather_than_guessing():
    built = steady("2024-09-01", 5, "10")
    assert built.day_units_reach("2024-09-01", 850) is None


def test_a_hole_stops_a_strict_walk_but_not_a_carried_one():
    built = series([("2024-09-01", 10), ("2024-09-03", 10), ("2024-09-04", 10)])
    assert built.day_units_reach("2024-09-01", 30) is None
    assert built.day_units_reach("2024-09-01", 30, policy=GapPolicy.CARRY_FORWARD) == date(
        2024, 9, 3
    )


def test_a_target_of_nothing_is_not_a_question():
    built = steady("2024-09-01", 5)
    with pytest.raises(ValidationError):
        built.day_units_reach("2024-09-01", 0)


def test_a_walk_gives_up_at_its_limit():
    built = steady("2024-09-01", 40, "1")
    assert built.day_units_reach("2024-09-01", 900, limit_days=10) is None


def test_a_projection_answers_before_the_series_exists():
    built = ThermalSeries()
    assert built.projected_day("2024-09-01", 850, 10) == date(2024, 11, 24)


def test_a_projection_below_the_zero_point_never_gets_there():
    built = ThermalSeries()
    with pytest.raises(ValidationError):
        built.projected_day("2024-09-01", 850, 4, zero_point_c=4)
