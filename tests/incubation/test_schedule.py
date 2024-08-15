from datetime import date
from decimal import Decimal

import pytest

from hatchlot.calendar import DateRange
from hatchlot.errors import ValidationError
from hatchlot.identifiers import LotCode
from hatchlot.incubation.development import Mark
from hatchlot.incubation.eggslot import EggLot, EggStage
from hatchlot.incubation.schedule import (
    busiest_week,
    next_after,
    of_mark,
    room_schedule,
    schedule_for,
    within,
    workload,
)
from hatchlot.water.thermal import ThermalSeries


def lot(sequence=1, green="10000", spawned="2024-09-13", stage=EggStage.GREEN):
    return EggLot(
        code=LotCode(2024, "CHK", sequence),
        take="T-001",
        species="CHK",
        spawned_on=date.fromisoformat(spawned),
        green_count=Decimal(green),
        stage=stage,
    )


def steady(start="2024-09-13", days=250, celsius="10"):
    series = ThermalSeries()
    day = date.fromisoformat(start)
    for offset in range(days):
        series.add(date.fromordinal(day.toordinal() + offset), celsius)
    return series


def test_a_lot_gets_its_three_marks_in_order():
    entries = schedule_for(lot(), steady())
    assert [entry.mark for entry in entries] == [Mark.EYE_UP, Mark.HATCH, Mark.SWIM_UP]
    assert [entry.day for entry in entries] == sorted(entry.day for entry in entries)


def test_marks_the_series_has_not_reached_are_left_out_without_a_projection():
    entries = schedule_for(lot(), steady(days=50))
    assert [entry.mark for entry in entries] == [Mark.EYE_UP]


def test_a_projection_fills_in_the_rest_and_says_so():
    entries = schedule_for(lot(), steady(days=50), projection_celsius=10)
    assert len(entries) == 3
    assert entries[0].projected is False
    assert entries[-1].projected is True
    assert "projected" in entries[-1].label


def test_an_entry_carries_the_eggs_that_are_actually_standing():
    eggs = lot(green="10000")
    entries = schedule_for(eggs, steady())
    assert entries[0].eggs == Decimal(10000)


def test_the_room_calendar_merges_every_lot_in_day_order():
    entries = room_schedule([lot(1), lot(2, spawned="2024-10-01")], steady())
    days = [entry.day for entry in entries]
    assert days == sorted(days)
    assert len({entry.lot for entry in entries}) == 2


def test_a_closed_lot_is_off_the_calendar():
    entries = room_schedule([lot(1, stage=EggStage.PONDED)], steady())
    assert entries == ()


def test_the_calendar_slices_by_window_and_by_mark():
    entries = room_schedule([lot(1), lot(2, spawned="2024-10-01")], steady())
    assert len(of_mark(entries, Mark.EYE_UP)) == 2
    assert len(within(entries, DateRange("2024-10-01", "2024-10-31"))) >= 1


def test_the_next_thing_after_a_day():
    entries = room_schedule([lot()], steady())
    following = next_after(entries, "2024-09-13")
    assert following is not None
    assert following.mark is Mark.EYE_UP
    assert next_after(entries, "2030-01-01") is None


def test_the_busiest_week_is_weighted_by_eggs_not_by_lots():
    small = [lot(1, green="1000"), lot(2, green="1000", spawned="2024-09-14")]
    big = lot(3, green="500000", spawned="2024-11-20")
    entries = room_schedule([*small, big], steady(days=300))
    window = busiest_week(entries)
    assert window is not None
    assert big.spawned_on <= window.end


def test_the_busiest_week_of_an_empty_calendar_is_nothing():
    assert busiest_week(()) is None


def test_the_workload_in_a_window_is_split_by_mark():
    entries = room_schedule([lot(green="10000")], steady())
    totals = workload(entries, DateRange("2024-09-13", "2025-06-01"))
    assert totals[Mark.EYE_UP] == Decimal(10000)
    assert set(totals) == {Mark.EYE_UP, Mark.HATCH, Mark.SWIM_UP}


def test_a_window_nothing_falls_in_is_an_empty_workload():
    entries = room_schedule([lot()], steady())
    assert workload(entries, DateRange("2024-09-13", "2024-09-20")) == {}


def test_a_planning_window_of_years_is_refused():
    entries = room_schedule([lot()], steady())
    with pytest.raises(ValidationError):
        workload(entries, DateRange("2024-01-01", "2026-01-01"))
