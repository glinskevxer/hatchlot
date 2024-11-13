from decimal import Decimal

import pytest

from hatchlot.calendar import DateRange
from hatchlot.errors import ValidationError
from hatchlot.feed.feeding import (
    Feeding,
    FeedingLog,
    FeedMethod,
    feed_by_lot,
    feed_cost,
    feed_per_fish,
)
from hatchlot.quantities.base import Quantity

LOT = "2024-CHK-01"
MARCH = DateRange("2025-03-01", "2025-03-31")


def feeding(day, kilograms, lot=LOT, method=FeedMethod.HAND, feed_lot="FL-001"):
    return Feeding(day, lot, Quantity(str(kilograms), "kg"), method, feed_lot, "kt")


def log(*entries):
    book = FeedingLog()
    for entry in entries:
        book.record(entry)
    return book


def test_a_feeding_normalises_both_lots_and_keeps_the_person():
    entry = feeding("2025-03-01", 10, lot=" 2024 chk 01 ", feed_lot=" fl 001 ")
    assert entry.lot == LOT
    assert entry.feed_lot == "FL-001"
    assert entry.fed_by == "kt"


def test_a_feeding_needs_an_amount_a_method_and_a_person():
    with pytest.raises(ValidationError):
        feeding("2025-03-01", 0)
    with pytest.raises(ValidationError):
        Feeding("2025-03-01", LOT, Quantity(1, "kg"), "hand", "FL-001", "kt")  # type: ignore[arg-type]
    with pytest.raises(ValidationError):
        Feeding("2025-03-01", LOT, Quantity(1, "kg"), FeedMethod.HAND, "FL-001", " ")


def test_a_demand_feeder_is_the_one_that_is_not_weighed():
    assert FeedMethod.HAND.is_measured
    assert FeedMethod.BELT.is_measured
    assert not FeedMethod.DEMAND.is_measured


def test_totals_over_a_lot_and_a_window():
    book = log(feeding("2025-03-01", 10), feeding("2025-04-01", 5))
    assert book.fed(LOT) == Quantity(15, "kg")
    assert book.fed(LOT, MARCH) == Quantity(10, "kg")
    assert book.fed("2024-CHK-09") == Quantity(0, "kg")


def test_several_feedings_on_one_day_add_up():
    book = log(feeding("2025-03-01", 4), feeding("2025-03-01", 6))
    assert book.fed_on(LOT, "2025-03-01") == Quantity(10, "kg")
    assert book.fed_on(LOT, "2025-03-02") == Quantity(0, "kg")


def test_which_feed_lots_went_into_a_fish_lot():
    book = log(
        feeding("2025-03-01", 10, feed_lot="FL-001"),
        feeding("2025-03-05", 10, feed_lot="FL-002"),
        feeding("2025-04-05", 10, feed_lot="FL-003"),
    )
    assert book.feed_lots_used(LOT) == ("FL-001", "FL-002", "FL-003")
    assert book.feed_lots_used(LOT, MARCH) == ("FL-001", "FL-002")


def test_how_many_days_a_lot_was_fed_in_a_window():
    book = log(feeding("2025-03-01", 4), feeding("2025-03-01", 6), feeding("2025-03-02", 10))
    assert book.days_fed(LOT, MARCH) == 2


def test_a_day_against_its_plan_is_signed():
    book = log(feeding("2025-03-01", 9))
    assert book.against_plan(LOT, "2025-03-01", Quantity(10, "kg")) == Decimal(-10)
    assert book.against_plan(LOT, "2025-03-01", Quantity(9, "kg")) == Decimal(0)
    with pytest.raises(ValidationError):
        book.against_plan(LOT, "2025-03-01", Quantity(0, "kg"))


def test_a_lot_eating_well_is_not_off_feed():
    book = log(*[feeding(f"2025-03-{day:02d}", 10) for day in range(1, 32)])
    assert not book.is_off_feed(LOT, MARCH, Quantity(10, "kg"))


def test_a_lot_eating_half_of_what_it_should_is_off_feed():
    book = log(*[feeding(f"2025-03-{day:02d}", 5) for day in range(1, 32)])
    assert book.is_off_feed(LOT, MARCH, Quantity(10, "kg"))
    assert not book.is_off_feed(LOT, MARCH, Quantity(10, "kg"), share="0.4")


def test_an_impossible_off_feed_share_is_refused():
    book = log(feeding("2025-03-01", 5))
    with pytest.raises(ValidationError):
        book.is_off_feed(LOT, MARCH, Quantity(10, "kg"), share=0)
    with pytest.raises(ValidationError):
        book.is_off_feed(LOT, MARCH, Quantity(10, "kg"), share="1.5")


def test_the_share_of_feed_that_was_actually_weighed():
    book = log(
        feeding("2025-03-01", 75, method=FeedMethod.HAND),
        feeding("2025-03-02", 25, method=FeedMethod.DEMAND),
    )
    assert book.hand_fed_share(LOT) == Decimal("0.75")
    assert FeedingLog().hand_fed_share(LOT) == Decimal(0)


def test_everything_fed_in_a_window_split_by_lot():
    book = log(
        feeding("2025-03-01", 10),
        feeding("2025-03-02", 5, lot="2024-CHK-02"),
        feeding("2025-04-01", 99),
    )
    totals = feed_by_lot(book, MARCH)
    assert totals[LOT] == Quantity(10, "kg")
    assert totals["2024-CHK-02"] == Quantity(5, "kg")
    assert "2024-CHK-03" not in totals


def test_what_the_feed_cost():
    assert feed_cost(Quantity(100, "kg"), "2.50") == Decimal(250)
    assert feed_cost(Quantity(0, "kg"), "2.50") == Decimal(0)
    with pytest.raises(ValidationError):
        feed_cost(Quantity(100, "kg"), "-1")


def test_the_feed_one_fish_got():
    assert feed_per_fish(Quantity(10, "kg"), 10000) == Quantity(1, "g")
    with pytest.raises(ValidationError):
        feed_per_fish(Quantity(10, "kg"), 0)
