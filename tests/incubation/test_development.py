from datetime import date
from decimal import Decimal

import pytest

from hatchlot.errors import PolicyError, ValidationError
from hatchlot.incubation.development import (
    Mark,
    accumulated,
    all_milestones,
    check_handling,
    development_stage,
    is_tender,
    milestone,
    units_for,
)
from hatchlot.species import species
from hatchlot.water.thermal import ThermalSeries

CHINOOK = species("CHK")


def steady(start="2024-09-13", days=200, celsius="10"):
    series = ThermalSeries()
    day = date.fromisoformat(start)
    for offset in range(days):
        series.add(date.fromordinal(day.toordinal() + offset), celsius)
    return series


def test_the_marks_come_off_the_species_table():
    assert units_for(CHINOOK, Mark.EYE_UP) == Decimal(425)
    assert units_for(CHINOOK, Mark.HATCH) == Decimal(850)
    assert units_for(CHINOOK, Mark.SWIM_UP) == Decimal(1300)


def test_the_accumulation_between_the_take_and_a_day():
    series = steady()
    assert accumulated(series, "2024-09-13", "2024-09-22", CHINOOK) == Decimal(100)


def test_an_accumulation_before_the_take_is_refused():
    with pytest.raises(ValidationError):
        accumulated(steady(), "2024-09-13", "2024-09-01", CHINOOK)


def test_a_mark_the_water_has_already_passed_is_not_a_projection():
    found = milestone(steady(), "2024-09-13", CHINOOK, Mark.EYE_UP)
    assert not found.projected
    assert found.is_reached
    assert found.day == date(2024, 10, 25)


def test_a_mark_the_series_has_not_reached_answers_nothing_without_a_water():
    found = milestone(steady(days=10), "2024-09-13", CHINOOK, Mark.HATCH)
    assert found.day is None
    assert found.projected
    assert not found.is_reached


def test_a_projection_carries_on_from_where_the_series_stops():
    found = milestone(steady(days=10), "2024-09-13", CHINOOK, Mark.HATCH, projection_celsius=10)
    assert found.projected
    assert found.day is not None
    assert found.day > date(2024, 9, 22)


def test_a_projection_on_an_empty_series_starts_at_the_take():
    found = milestone(ThermalSeries(), "2024-09-13", CHINOOK, Mark.EYE_UP, projection_celsius=10)
    assert found.projected
    assert found.day == date(2024, 10, 25)


def test_a_warmer_projection_lands_sooner():
    warm = milestone(ThermalSeries(), "2024-09-13", CHINOOK, Mark.HATCH, projection_celsius=12)
    cold = milestone(ThermalSeries(), "2024-09-13", CHINOOK, Mark.HATCH, projection_celsius=8)
    assert warm.day is not None and cold.day is not None
    assert warm.day < cold.day


def test_every_mark_comes_back_in_order():
    marks = all_milestones(steady(), "2024-09-13", CHINOOK)
    assert [found.mark for found in marks] == [Mark.EYE_UP, Mark.HATCH, Mark.SWIM_UP]
    days = [found.day for found in marks if found.day is not None]
    assert days == sorted(days)


def test_the_tender_window_opens_a_day_in_and_shuts_at_eye_up():
    assert not is_tender(0, CHINOOK)
    assert not is_tender(23, CHINOOK)
    assert is_tender(24, CHINOOK)
    assert is_tender(424, CHINOOK)
    assert not is_tender(425, CHINOOK)


def test_negative_units_are_refused():
    with pytest.raises(ValidationError):
        is_tender(-1, CHINOOK)


def test_handling_inside_the_tender_window_is_refused_by_name():
    with pytest.raises(PolicyError) as excinfo:
        check_handling(200, CHINOOK)
    assert excinfo.value.rule == "incubation.tender"


def test_handling_a_fresh_or_an_eyed_lot_passes_quietly():
    check_handling(10, CHINOOK)
    check_handling(500, CHINOOK)


def test_the_tender_window_is_shorter_for_a_species_that_eyes_up_sooner():
    steelhead = species("STH")
    assert is_tender(300, CHINOOK)
    assert not is_tender(300, steelhead)


def test_the_stage_a_lot_has_reached():
    assert development_stage(100, CHINOOK) is None
    assert development_stage(500, CHINOOK) is Mark.EYE_UP
    assert development_stage(900, CHINOOK) is Mark.HATCH
    assert development_stage(1400, CHINOOK) is Mark.SWIM_UP
