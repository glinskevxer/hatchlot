from datetime import datetime
from decimal import Decimal

import pytest

from hatchlot.calendar import DateRange
from hatchlot.errors import ValidationError
from hatchlot.quantities.temperature import Temperature
from hatchlot.water.monitoring import (
    ExcursionKind,
    MonitoringLog,
    Reading,
    Thresholds,
)


def reading(stamp, container="RW-1", celsius="10", oxygen="9"):
    return Reading(stamp, container, Temperature(celsius, "C"), oxygen)


def test_a_reading_normalises_its_unit_and_keeps_its_temperature():
    entry = reading("2024-09-01 08:00", container=" rw 1 ", celsius="50")
    assert entry.container == "RW-1"
    assert entry.temperature == Temperature(50, "C")


def test_a_negative_oxygen_reading_is_refused():
    with pytest.raises(ValidationError):
        reading("2024-09-01 08:00", oxygen="-1")


def test_an_inverted_threshold_band_is_refused():
    with pytest.raises(ValidationError):
        Thresholds(minimum_celsius=Decimal(20), maximum_celsius=Decimal(10))


def test_a_negative_oxygen_threshold_is_refused():
    with pytest.raises(ValidationError):
        Thresholds(minimum_oxygen_mgL=Decimal(-1))


def test_one_reading_can_cross_two_lines_at_once():
    entry = reading("2024-09-01 08:00", celsius="18", oxygen="4")
    assert set(entry.breaches(Thresholds())) == {
        ExcursionKind.LOW_OXYGEN,
        ExcursionKind.HIGH_TEMPERATURE,
    }


def test_a_good_reading_crosses_nothing():
    assert reading("2024-09-01 08:00").breaches(Thresholds()) == ()


def test_cold_water_is_its_own_kind_of_excursion():
    entry = reading("2024-09-01 08:00", celsius="1")
    assert entry.breaches(Thresholds()) == (ExcursionKind.LOW_TEMPERATURE,)


def test_the_log_keeps_readings_in_time_order_however_they_arrive():
    log = MonitoringLog(
        [reading("2024-09-02 08:00"), reading("2024-09-01 08:00"), reading("2024-09-01 16:00")]
    )
    assert [entry.taken_at.day for entry in log] == [1, 1, 2]
    assert len(log) == 3


def test_the_log_can_be_asked_for_one_unit_or_one_window():
    log = MonitoringLog(
        [
            reading("2024-09-01 08:00", container="RW-1"),
            reading("2024-09-01 08:05", container="RW-2"),
            reading("2024-09-20 08:00", container="RW-1"),
        ]
    )
    assert log.containers() == ("RW-1", "RW-2")
    assert len(log.for_container("rw 1")) == 2
    assert len(log.within(DateRange("2024-09-01", "2024-09-02"))) == 2


def test_the_latest_reading_on_a_unit_and_on_a_unit_with_none():
    log = MonitoringLog([reading("2024-09-01 08:00"), reading("2024-09-01 16:00", oxygen="8")])
    latest = log.latest("RW-1")
    assert latest is not None
    assert latest.oxygen_mgL == Decimal(8)
    assert log.latest("RW-9") is None


def test_the_mean_oxygen_on_a_unit_and_the_refusal_when_there_is_none():
    log = MonitoringLog(
        [reading("2024-09-01 08:00", oxygen="8"), reading("2024-09-01 16:00", oxygen="10")]
    )
    assert log.mean_oxygen("RW-1") == Decimal(9)
    with pytest.raises(ValidationError):
        log.mean_oxygen("RW-9")


def test_a_clean_log_has_no_excursions():
    log = MonitoringLog([reading("2024-09-01 08:00"), reading("2024-09-01 16:00")])
    assert log.excursions() == ()


def test_consecutive_bad_readings_collapse_into_one_excursion():
    log = MonitoringLog(
        [
            reading("2024-09-01 08:00", oxygen="5.5"),
            reading("2024-09-01 12:00", oxygen="4.8"),
            reading("2024-09-01 16:00", oxygen="5.9"),
        ]
    )
    found = log.excursions()
    assert len(found) == 1
    assert found[0].kind is ExcursionKind.LOW_OXYGEN
    assert found[0].readings == 3
    assert found[0].worst == Decimal("4.8")
    assert found[0].duration_hours == Decimal(8)


def test_a_good_reading_closes_an_excursion_and_a_later_bad_one_opens_another():
    log = MonitoringLog(
        [
            reading("2024-09-01 08:00", oxygen="5.5"),
            reading("2024-09-01 12:00", oxygen="9.0"),
            reading("2024-09-01 16:00", oxygen="5.0"),
        ]
    )
    found = log.excursions()
    assert len(found) == 2
    assert [entry.readings for entry in found] == [1, 1]


def test_two_units_do_not_share_an_excursion():
    log = MonitoringLog(
        [
            reading("2024-09-01 08:00", container="RW-1", oxygen="5.5"),
            reading("2024-09-01 09:00", container="RW-2", oxygen="5.5"),
        ]
    )
    found = log.excursions()
    assert {entry.container for entry in found} == {"RW-1", "RW-2"}


def test_a_reading_that_is_wrong_two_ways_makes_two_excursions():
    log = MonitoringLog([reading("2024-09-01 08:00", celsius="18", oxygen="4")])
    found = log.excursions()
    assert {entry.kind for entry in found} == {
        ExcursionKind.LOW_OXYGEN,
        ExcursionKind.HIGH_TEMPERATURE,
    }


def test_the_worst_value_is_the_extreme_in_the_direction_that_hurts():
    log = MonitoringLog(
        [reading("2024-09-01 08:00", celsius="17"), reading("2024-09-01 12:00", celsius="19")]
    )
    assert log.excursions()[0].worst == Decimal(19)
    cold = MonitoringLog(
        [reading("2024-09-01 08:00", celsius="1"), reading("2024-09-01 12:00", celsius="0.5")]
    )
    assert cold.excursions()[0].worst == Decimal("0.5")


def test_an_excursion_still_open_at_the_end_of_the_log_is_still_reported():
    log = MonitoringLog([reading("2024-09-01 08:00", oxygen="4")])
    found = log.excursions()
    assert len(found) == 1
    assert found[0].ended_at == datetime(2024, 9, 1, 8, 0)
    assert found[0].duration_hours == Decimal(0)


def test_moving_the_thresholds_changes_what_counts():
    log = MonitoringLog([reading("2024-09-01 08:00", oxygen="6.5")])
    assert log.excursions() == ()
    assert len(log.excursions(Thresholds(minimum_oxygen_mgL=Decimal(7)))) == 1
