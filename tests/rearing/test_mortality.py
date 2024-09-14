from decimal import Decimal

import pytest

from hatchlot.calendar import DateRange
from hatchlot.errors import ValidationError
from hatchlot.rearing.mortality import (
    MortalityCause,
    MortalityLog,
    MortalityRecord,
    cumulative_survival,
)

LOT = "2024-CHK-01"


def record(day, count, cause=MortalityCause.UNKNOWN, lot=LOT):
    return MortalityRecord(day, lot, count, cause, "kt")


def log(*records):
    book = MortalityLog()
    for entry in records:
        book.record(entry)
    return book


def test_a_record_normalises_its_lot_and_keeps_its_recorder():
    entry = record("2025-02-01", 50)
    assert entry.lot == LOT
    assert entry.recorded_by == "kt"


def test_a_record_needs_a_count_a_cause_and_a_person():
    with pytest.raises(ValidationError):
        record("2025-02-01", 0)
    with pytest.raises(ValidationError):
        MortalityRecord("2025-02-01", LOT, 10, "disease", "kt")  # type: ignore[arg-type]
    with pytest.raises(ValidationError):
        MortalityRecord("2025-02-01", LOT, 10, MortalityCause.DISEASE, " ")


def test_the_causes_a_station_is_answerable_for():
    assert MortalityCause.HANDLING.is_preventable
    assert MortalityCause.OXYGEN.is_preventable
    assert not MortalityCause.PREDATION.is_preventable
    assert not MortalityCause.UNKNOWN.is_preventable


def test_totals_over_a_lot_and_over_a_window():
    book = log(record("2025-02-01", 50), record("2025-03-01", 30))
    assert book.total(LOT) == Decimal(80)
    assert book.total(LOT, DateRange("2025-02-01", "2025-02-28")) == Decimal(50)
    assert book.total("2024-CHK-09") == Decimal(0)


def test_the_cause_split_and_its_window():
    book = log(
        record("2025-02-01", 50, MortalityCause.DISEASE),
        record("2025-02-02", 30, MortalityCause.PREDATION),
        record("2025-03-01", 20, MortalityCause.DISEASE),
    )
    assert book.by_cause(LOT)[MortalityCause.DISEASE] == Decimal(70)
    february = book.by_cause(LOT, DateRange("2025-02-01", "2025-02-28"))
    assert february[MortalityCause.DISEASE] == Decimal(50)
    assert february[MortalityCause.PREDATION] == Decimal(30)


def test_the_share_the_station_is_answerable_for():
    book = log(
        record("2025-02-01", 75, MortalityCause.HANDLING),
        record("2025-02-02", 25, MortalityCause.PREDATION),
    )
    assert book.preventable_share(LOT) == Decimal("0.75")
    assert MortalityLog().preventable_share(LOT) == Decimal(0)


def test_the_daily_rate_is_per_thousand_fish():
    book = log(record("2025-02-01", 50))
    assert book.daily_rate(LOT, "2025-02-01", 50000) == Decimal(1)
    assert book.daily_rate(LOT, "2025-02-02", 50000) == Decimal(0)


def test_two_records_on_one_day_add_into_the_rate():
    book = log(record("2025-02-01", 50), record("2025-02-01", 50))
    assert book.daily_rate(LOT, "2025-02-01", 50000) == Decimal(2)


def test_a_rate_against_no_population_is_refused():
    with pytest.raises(ValidationError):
        log(record("2025-02-01", 50)).daily_rate(LOT, "2025-02-01", 0)


def test_the_rolling_rate_spreads_the_window_out():
    book = log(record("2025-02-01", 70))
    assert book.rolling_rate(LOT, "2025-02-07", 10000, days=7) == Decimal(1)
    assert book.rolling_rate(LOT, "2025-02-07", 10000, days=1) == Decimal(0)


def test_a_rolling_window_of_no_days_is_refused():
    with pytest.raises(ValidationError):
        log(record("2025-02-01", 70)).rolling_rate(LOT, "2025-02-07", 10000, days=0)


def test_an_event_is_a_day_over_the_station_line():
    book = log(record("2025-02-01", 500))
    assert book.is_event(LOT, "2025-02-01", 50000)
    assert not book.is_event(LOT, "2025-02-01", 50000, threshold=20)
    with pytest.raises(ValidationError):
        book.is_event(LOT, "2025-02-01", 50000, threshold=0)


def test_the_worst_day_on_a_lot():
    book = log(record("2025-02-01", 50), record("2025-02-05", 500))
    worst = book.worst_day(LOT)
    assert worst is not None
    assert worst.count == Decimal(500)
    assert MortalityLog().worst_day(LOT) is None


def test_the_log_slices_by_window_across_lots():
    book = log(
        record("2025-02-01", 50),
        record("2025-02-01", 20, lot="2024-CHK-02"),
        record("2025-04-01", 10),
    )
    assert len(book.within(DateRange("2025-02-01", "2025-02-28"))) == 2
    assert len(book) == 3


def test_cumulative_survival_against_the_ponded_number():
    assert cumulative_survival(10000, 1000) == Decimal("0.9")
    assert cumulative_survival(10000, 0) == Decimal(1)


def test_more_dead_than_were_ponded_is_refused():
    with pytest.raises(ValidationError):
        cumulative_survival(1000, 2000)
    with pytest.raises(ValidationError):
        cumulative_survival(0, 0)
