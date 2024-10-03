from datetime import date
from decimal import Decimal

import pytest

from hatchlot.calendar import DateRange
from hatchlot.errors import ValidationError
from hatchlot.quantities.base import Quantity
from hatchlot.rearing.cleaning import (
    Cleaning,
    CleaningLog,
    CleaningMethod,
    capture_share,
    cleaning_interval,
    expected_solids,
    kind_interval,
    solids_from_feed,
)
from hatchlot.rearing.container import Container, ContainerKind


def container(code="RW-1", kind=ContainerKind.RACEWAY, length="30"):
    return Container(
        code=code,
        kind=kind,
        length=Quantity(length, "m"),
        width=Quantity(3, "m"),
        depth=Quantity(1, "m"),
        flow=Quantity(500, "gpm"),
    )


def cleaning(day, code="RW-1", method=CleaningMethod.BRUSH, solids="5"):
    return Cleaning(day, code, method, "kt", Quantity(solids, "kg") if solids else None)


def test_a_cleaning_normalises_its_unit_and_keeps_its_person():
    entry = cleaning("2025-03-01", code=" rw 1 ")
    assert entry.container == "RW-1"
    assert entry.cleaned_by == "kt"


def test_a_cleaning_needs_a_person_a_real_method_and_sane_solids():
    with pytest.raises(ValidationError):
        Cleaning("2025-03-01", "RW-1", CleaningMethod.BRUSH, " ")
    with pytest.raises(ValidationError):
        Cleaning("2025-03-01", "RW-1", "brush", "kt")  # type: ignore[arg-type]
    with pytest.raises(ValidationError):
        Cleaning("2025-03-01", "RW-1", CleaningMethod.BRUSH, "kt", Quantity(-1, "kg"))


def test_a_flush_pushes_solids_downstream_rather_than_removing_them():
    assert CleaningMethod.BRUSH.removes_solids
    assert CleaningMethod.VACUUM.removes_solids
    assert not CleaningMethod.FLUSH.removes_solids


def test_the_solids_a_feed_leaves_behind():
    assert solids_from_feed(Quantity(100, "kg")) == Quantity("25.00", "kg")
    assert solids_from_feed(Quantity(100, "kg"), share="0.3") == Quantity("30.0", "kg")


def test_an_impossible_solids_share_is_refused():
    with pytest.raises(ValidationError):
        solids_from_feed(Quantity(100, "kg"), share="1.5")
    with pytest.raises(ValidationError):
        solids_from_feed(Quantity(-1, "kg"))


def test_a_heavier_raceway_fouls_faster():
    light = cleaning_interval(container(), Quantity(100, "kg"))
    heavy = cleaning_interval(container(), Quantity(2000, "kg"))
    assert heavy < light


def test_an_empty_unit_gets_the_base_interval():
    assert cleaning_interval(container(), Quantity(0, "kg")) == 14


def test_a_self_cleaning_unit_gets_longer_between_cleanings():
    circular = container(kind=ContainerKind.CIRCULAR)
    assert cleaning_interval(circular, Quantity(500, "kg")) > cleaning_interval(
        container(), Quantity(500, "kg")
    )
    assert kind_interval(ContainerKind.CIRCULAR) == 28
    assert kind_interval(ContainerKind.RACEWAY) == 14


def test_the_interval_never_falls_below_a_day():
    assert cleaning_interval(container(), Quantity(100000, "kg")) == 1


def test_an_interval_of_no_days_is_refused():
    with pytest.raises(ValidationError):
        cleaning_interval(container(), Quantity(100, "kg"), base_days=0)
    with pytest.raises(ValidationError):
        kind_interval(ContainerKind.RACEWAY, base_days=0)


def test_the_log_finds_when_a_unit_was_last_cleaned():
    log = CleaningLog([cleaning("2025-03-01"), cleaning("2025-03-20")])
    assert log.last_cleaned("RW-1") == date(2025, 3, 20)
    assert log.last_cleaned("RW-9") is None
    assert len(log) == 2


def test_only_what_was_taken_out_counts_toward_the_solids():
    log = CleaningLog(
        [
            cleaning("2025-03-01", solids="5"),
            cleaning("2025-03-10", method=CleaningMethod.FLUSH, solids="20"),
            cleaning("2025-03-20", method=CleaningMethod.VACUUM, solids="7"),
        ]
    )
    assert log.solids_removed() == Quantity(12, "kg")
    assert log.solids_removed(DateRange("2025-03-01", "2025-03-05")) == Quantity(5, "kg")


def test_a_cleaning_with_no_solids_recorded_adds_nothing():
    log = CleaningLog([cleaning("2025-03-01", solids="")])
    assert log.solids_removed() == Quantity(0, "kg")


def test_when_a_unit_falls_due_next():
    log = CleaningLog([cleaning("2025-03-01")])
    due = log.due_on(container(), Quantity(100, "kg"))
    assert due is not None
    assert due > date(2025, 3, 1)


def test_a_unit_never_cleaned_is_overdue_and_has_no_due_date():
    log = CleaningLog()
    assert log.due_on(container(), Quantity(100, "kg")) is None
    assert log.is_overdue(container(), Quantity(100, "kg"), "2025-03-01")


def test_a_recently_cleaned_unit_is_not_overdue():
    log = CleaningLog([cleaning("2025-03-01")])
    assert not log.is_overdue(container(), Quantity(100, "kg"), "2025-03-05")
    assert log.is_overdue(container(), Quantity(100, "kg"), "2025-05-01")


def test_the_solids_a_station_should_have_taken_out():
    assert expected_solids({"RW-1": Quantity(100, "kg"), "RW-2": Quantity(100, "kg")}) == Quantity(
        50, "kg"
    )
    assert expected_solids({}) == Quantity(0, "kg")


def test_the_share_of_the_expected_solids_actually_captured():
    assert capture_share(Quantity(25, "kg"), Quantity(50, "kg")) == Decimal("0.5")
    with pytest.raises(ValidationError):
        capture_share(Quantity(25, "kg"), Quantity(0, "kg"))
