from datetime import date, datetime

import pytest

from hatchlot.calendar import (
    DateRange,
    add_months,
    brood_year_of,
    brood_year_range,
    days_between,
    parse_date,
    parse_timestamp,
)
from hatchlot.errors import ValidationError


@pytest.mark.parametrize(
    "raw", ["2024-09-13", "09/13/2024", "13 Sep 2024", "20240913", date(2024, 9, 13)]
)
def test_the_forms_a_date_arrives_in(raw):
    assert parse_date(raw) == date(2024, 9, 13)


def test_a_datetime_is_read_as_its_day():
    assert parse_date(datetime(2024, 9, 13, 6, 30)) == date(2024, 9, 13)


@pytest.mark.parametrize("bad", ["", "   ", "13/13/2024", "not a date", 7, None])
def test_junk_is_refused_as_a_date(bad):
    with pytest.raises(ValidationError):
        parse_date(bad)


@pytest.mark.parametrize(
    "raw",
    ["2024-09-13 06:30:00", "2024-09-13T06:30", "09/13/2024 06:30"],
)
def test_a_datalogger_timestamp_reads_with_or_without_seconds(raw):
    assert parse_timestamp(raw) == datetime(2024, 9, 13, 6, 30)


def test_a_timestamp_with_no_time_falls_back_to_midnight():
    assert parse_timestamp("2024-09-13") == datetime(2024, 9, 13, 0, 0)
    assert parse_timestamp(date(2024, 9, 13)) == datetime(2024, 9, 13, 0, 0)


def test_a_datetime_timestamp_comes_back_unchanged():
    stamp = datetime(2024, 9, 13, 6, 30, 15)
    assert parse_timestamp(stamp) is stamp


@pytest.mark.parametrize("bad", ["", 7, None])
def test_junk_is_refused_as_a_timestamp(bad):
    with pytest.raises(ValidationError):
        parse_timestamp(bad)


def test_a_range_counts_both_of_its_ends():
    assert DateRange("2024-03-01", "2024-03-31").days == 31
    assert DateRange("2024-03-01", "2024-03-01").days == 1


def test_a_backwards_range_is_refused():
    with pytest.raises(ValidationError):
        DateRange("2024-03-31", "2024-03-01")


def test_membership_includes_both_ends():
    window = DateRange("2024-03-01", "2024-03-31")
    assert date(2024, 3, 1) in window
    assert date(2024, 3, 31) in window
    assert date(2024, 2, 29) not in window
    assert "2024-04-01" not in window


def test_iterating_a_range_yields_every_day_once():
    days = list(DateRange("2024-02-27", "2024-03-02"))
    assert days[0] == date(2024, 2, 27)
    assert len(days) == 5
    assert days[-1] == date(2024, 3, 2)


def test_overlap_and_intersection_agree_with_each_other():
    march = DateRange("2024-03-01", "2024-03-31")
    mid = DateRange("2024-03-15", "2024-04-15")
    away = DateRange("2024-05-01", "2024-05-31")
    assert march.overlaps(mid)
    assert not march.overlaps(away)
    assert march.intersection(mid) == DateRange("2024-03-15", "2024-03-31")
    assert march.intersection(away) is None


def test_clipping_to_a_range_that_never_meets_is_refused():
    march = DateRange("2024-03-01", "2024-03-31")
    assert march.clipped_to(DateRange("2024-03-10", "2024-06-01")).days == 22
    with pytest.raises(ValidationError):
        march.clipped_to(DateRange("2024-05-01", "2024-05-31"))


def test_extending_pushes_the_end_out_only():
    extended = DateRange("2024-03-01", "2024-03-31").extended(10)
    assert extended.start == date(2024, 3, 1)
    assert extended.end == date(2024, 4, 10)


def test_a_range_prints_and_parses_back():
    window = DateRange("2024-03-01", "2024-03-31")
    assert str(window) == "2024-03-01..2024-03-31"
    assert DateRange.parse(" 2024-03-01 .. 2024-03-31 ") == window


def test_a_range_with_no_separator_is_refused():
    with pytest.raises(ValidationError):
        DateRange.parse("2024-03-01")


def test_the_month_of_a_day_covers_that_month_including_a_leap_february():
    assert DateRange.month_of("2024-02-11").days == 29
    assert DateRange.month_of("2023-02-11").days == 28
    assert DateRange.month_of("2024-12-25") == DateRange("2024-12-01", "2024-12-31")


def test_ranges_sort_by_their_start_then_their_end():
    ranges = [
        DateRange("2024-03-01", "2024-03-31"),
        DateRange("2024-01-01", "2024-12-31"),
        DateRange("2024-03-01", "2024-03-15"),
    ]
    assert [str(r) for r in sorted(ranges)][0] == "2024-01-01..2024-12-31"


def test_the_brood_year_runs_from_the_month_the_take_starts():
    assert brood_year_of("2024-09-13") == 2024
    assert brood_year_of("2025-03-01") == 2024
    assert brood_year_of("2025-07-01") == 2025


def test_a_station_that_starts_in_january_gets_the_calendar_year():
    assert brood_year_of("2024-03-01", start_month=1) == 2024


def test_the_brood_year_window_is_a_year_long_and_starts_where_it_should():
    window = brood_year_range(2024)
    assert window.start == date(2024, 7, 1)
    assert window.end == date(2025, 6, 30)
    assert window.days == 365


@pytest.mark.parametrize("bad", [0, 13])
def test_an_impossible_start_month_is_refused(bad):
    with pytest.raises(ValidationError):
        brood_year_of("2024-09-13", start_month=bad)
    with pytest.raises(ValidationError):
        brood_year_range(2024, start_month=bad)


def test_adding_months_lands_on_the_last_day_of_a_short_month():
    assert add_months("2024-01-31", 1) == date(2024, 2, 29)
    assert add_months("2023-01-31", 1) == date(2023, 2, 28)
    assert add_months("2024-01-15", 12) == date(2025, 1, 15)


def test_adding_months_goes_backwards_too():
    assert add_months("2024-03-31", -1) == date(2024, 2, 29)
    assert add_months("2024-01-15", -1) == date(2023, 12, 15)


def test_days_between_is_signed():
    assert days_between("2024-03-01", "2024-03-31") == 30
    assert days_between("2024-03-31", "2024-03-01") == -30
