from datetime import date
from decimal import Decimal

import pytest

from hatchlot.errors import ValidationError
from hatchlot.growth.model import GrowthModel
from hatchlot.growth.projection import (
    meets_target,
    project_to_date,
    project_to_size,
    required_temperature,
)
from hatchlot.numeric import quantize
from hatchlot.quantities.base import Quantity
from hatchlot.water.thermal import ThermalSeries

MODEL = GrowthModel(coefficient=Decimal(2))


def steady(start="2025-01-01", days=100, celsius="10"):
    series = ThermalSeries()
    first = date.fromisoformat(start)
    for offset in range(days):
        series.add(date.fromordinal(first.toordinal() + offset), celsius)
    return series


def test_a_projection_inside_the_record_needs_no_assumption():
    projection = project_to_date(MODEL, Quantity(1, "g"), "2025-01-01", "2025-04-10", steady())
    assert projection.is_measured
    assert projection.thermal_units == Decimal(1000)
    assert quantize(projection.end_weight.to("g").amount, 2) == Decimal("27.00")
    assert projection.days == 99


def test_the_gain_is_the_difference_in_weight():
    projection = project_to_date(MODEL, Quantity(1, "g"), "2025-01-01", "2025-04-10", steady())
    assert quantize(projection.gain.to("g").amount, 2) == Decimal("26.00")


def test_a_projection_past_the_record_needs_an_assumed_water():
    with pytest.raises(ValidationError):
        project_to_date(MODEL, Quantity(1, "g"), "2025-01-01", "2025-06-01", steady())
    projection = project_to_date(
        MODEL, Quantity(1, "g"), "2025-01-01", "2025-06-01", steady(), assumed_celsius=10
    )
    assert not projection.is_measured
    assert projection.assumed_celsius == Decimal(10)


def test_a_projection_with_no_record_at_all_runs_on_the_assumption():
    projection = project_to_date(
        MODEL, Quantity(1, "g"), "2025-01-01", "2025-04-10", ThermalSeries(), assumed_celsius=10
    )
    assert projection.thermal_units == Decimal(1000)


def test_a_projection_starting_after_the_record_ends_runs_on_the_assumption():
    projection = project_to_date(
        MODEL,
        Quantity(1, "g"),
        "2026-01-01",
        "2026-01-10",
        steady(),
        assumed_celsius=10,
    )
    assert projection.thermal_units == Decimal(100)


def test_a_backwards_projection_is_refused():
    with pytest.raises(ValidationError):
        project_to_date(MODEL, Quantity(1, "g"), "2025-04-01", "2025-01-01", steady())


def test_an_assumed_water_of_nothing_is_refused():
    with pytest.raises(ValidationError):
        project_to_date(
            MODEL, Quantity(1, "g"), "2025-01-01", "2025-06-01", steady(), assumed_celsius=0
        )


def test_a_projection_to_a_size_answers_with_a_date():
    projection = project_to_size(MODEL, Quantity(1, "g"), Quantity(27, "g"), "2025-01-01", 10)
    assert projection.end_day == date(2025, 4, 11)
    assert projection.end_weight == Quantity(27, "g")
    assert projection.assumed_celsius == Decimal(10)


def test_colder_water_pushes_the_date_out():
    warm = project_to_size(MODEL, Quantity(1, "g"), Quantity(27, "g"), "2025-01-01", 12)
    cold = project_to_size(MODEL, Quantity(1, "g"), Quantity(27, "g"), "2025-01-01", 6)
    assert cold.end_day > warm.end_day


def test_a_projection_to_a_size_on_no_water_is_refused():
    with pytest.raises(ValidationError):
        project_to_size(MODEL, Quantity(1, "g"), Quantity(27, "g"), "2025-01-01", 0)


def test_a_projection_that_lands_inside_the_tolerance_meets_the_target():
    projection = project_to_date(MODEL, Quantity(1, "g"), "2025-01-01", "2025-04-10", steady())
    assert meets_target(projection, Quantity(27, "g"))
    assert meets_target(projection, Quantity(28, "g"))
    assert not meets_target(projection, Quantity(40, "g"))


def test_the_tolerance_can_be_tightened_to_nothing():
    projection = project_to_date(MODEL, Quantity(1, "g"), "2025-01-01", "2025-04-10", steady())
    assert not meets_target(projection, Quantity(28, "g"), tolerance=0)
    with pytest.raises(ValidationError):
        meets_target(projection, Quantity(27, "g"), tolerance="-0.1")


def test_the_water_a_schedule_would_need():
    needed = required_temperature(
        MODEL, Quantity(1, "g"), Quantity(27, "g"), "2025-01-01", "2025-04-11"
    )
    assert quantize(needed, 2) == Decimal("10.00")


def test_a_shorter_window_needs_warmer_water():
    long_way = required_temperature(
        MODEL, Quantity(1, "g"), Quantity(27, "g"), "2025-01-01", "2025-06-01"
    )
    short_way = required_temperature(
        MODEL, Quantity(1, "g"), Quantity(27, "g"), "2025-01-01", "2025-03-01"
    )
    assert short_way > long_way


def test_a_window_with_no_days_in_it_is_refused():
    with pytest.raises(ValidationError):
        required_temperature(MODEL, Quantity(1, "g"), Quantity(27, "g"), "2025-01-01", "2025-01-01")


def test_the_line_says_what_the_projection_assumed():
    measured = project_to_date(MODEL, Quantity(1, "g"), "2025-01-01", "2025-04-10", steady())
    assumed = project_to_size(MODEL, Quantity(1, "g"), Quantity(27, "g"), "2025-01-01", 10)
    assert "on the record" in measured.line()
    assert "assuming 10 degC" in assumed.line()
