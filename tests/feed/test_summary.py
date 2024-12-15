from datetime import date
from decimal import Decimal

import pytest

from hatchlot.calendar import DateRange
from hatchlot.errors import ValidationError
from hatchlot.feed import FeedingLog, summarise_feed
from hatchlot.feed.conversion import Conversion
from hatchlot.feed.feeding import Feeding, FeedMethod
from hatchlot.feed.feedlot import Analysis, FeedForm, FeedLot
from hatchlot.feed.store import FeedStore
from hatchlot.feed.summary import needs_ordering, reorder_point, share_of_feed
from hatchlot.quantities.base import Quantity

MARCH = DateRange("2025-03-01", "2025-03-31")
LOT = "2024-CHK-01"


def analysis():
    return Analysis(
        protein=Decimal("0.45"),
        fat=Decimal("0.16"),
        fibre=Decimal("0.02"),
        ash=Decimal("0.08"),
        moisture=Decimal("0.09"),
    )


def store(*specs):
    shed = FeedStore()
    for code, kilograms, made in specs:
        shed.add(
            FeedLot(
                code=code,
                product="starter",
                form=FeedForm.CRUMBLE,
                pellet_mm=Decimal("2.0"),
                analysis=analysis(),
                made_on=date.fromisoformat(made),
                quantity=Quantity(kilograms, "kg"),
            )
        )
    return shed


def log(*specs):
    book = FeedingLog()
    for day, kilograms, lot in specs:
        book.record(
            Feeding(day, lot, Quantity(str(kilograms), "kg"), FeedMethod.HAND, "FL-001", "kt")
        )
    return book


def conversion():
    return Conversion(
        fed=Quantity(310, "kg"),
        opening_biomass=Quantity(500, "kg"),
        closing_biomass=Quantity(750, "kg"),
        mortality_biomass=Quantity(10, "kg"),
    )


def test_a_month_of_feeding_adds_up_across_lots():
    summary = summarise_feed(
        log(("2025-03-01", 10, LOT), ("2025-03-02", 5, "2024-CHK-02")),
        store(("FL-001", "1000", "2025-02-01")),
        MARCH,
    )
    assert summary.fed == Quantity(15, "kg")
    assert summary.lots_fed == 2


def test_feeding_outside_the_window_is_not_counted():
    summary = summarise_feed(
        log(("2025-02-01", 100, LOT), ("2025-03-02", 5, LOT)),
        store(("FL-001", "1000", "2025-02-01")),
        MARCH,
    )
    assert summary.fed == Quantity(5, "kg")


def test_the_cost_and_the_daily_mean():
    summary = summarise_feed(
        log(("2025-03-01", 310, LOT)),
        store(("FL-001", "1000", "2025-02-01")),
        MARCH,
        price_per_kg="2.00",
    )
    assert summary.cost == Decimal(620)
    assert summary.daily_mean == Quantity(10, "kg")


def test_a_negative_price_is_refused():
    with pytest.raises(ValidationError):
        summarise_feed(FeedingLog(), FeedStore(), MARCH, price_per_kg="-1")


def test_how_long_the_store_lasts_at_the_current_rate():
    summary = summarise_feed(
        log(("2025-03-01", 310, LOT)),
        store(("FL-001", "1000", "2025-02-01")),
        MARCH,
    )
    assert summary.days_left == 100


def test_a_month_with_no_feeding_has_no_days_left_to_report():
    summary = summarise_feed(FeedingLog(), store(("FL-001", "1000", "2025-02-01")), MARCH)
    assert summary.days_left == 0
    assert summary.fed == Quantity(0, "kg")


def test_the_conversion_rides_along_when_it_is_given():
    summary = summarise_feed(
        log(("2025-03-01", 310, LOT)),
        store(("FL-001", "1000", "2025-02-01")),
        MARCH,
        conversion=conversion(),
    )
    assert summary.ratio == Decimal("1.24")
    assert "conversion 1.24" in summary.line()


def test_a_month_with_no_conversion_says_so():
    summary = summarise_feed(
        log(("2025-03-01", 310, LOT)), store(("FL-001", "1000", "2025-02-01")), MARCH
    )
    assert summary.ratio is None
    assert "no gain" in summary.line()


def test_a_conversion_with_no_gain_reads_as_no_gain():
    flat = Conversion(
        fed=Quantity(310, "kg"),
        opening_biomass=Quantity(500, "kg"),
        closing_biomass=Quantity(500, "kg"),
        mortality_biomass=Quantity(0, "kg"),
    )
    summary = summarise_feed(
        log(("2025-03-01", 310, LOT)),
        store(("FL-001", "1000", "2025-02-01")),
        MARCH,
        conversion=flat,
    )
    assert summary.ratio is None


def test_feed_going_out_of_date_is_named():
    summary = summarise_feed(
        FeedingLog(), store(("FL-001", "1000", "2024-12-01")), MARCH, expiring_days=90
    )
    assert summary.expiring == ("FL-001",)


def test_the_reorder_point_covers_the_lead_time_and_a_margin():
    summary = summarise_feed(
        log(("2025-03-01", 310, LOT)), store(("FL-001", "1000", "2025-02-01")), MARCH
    )
    assert reorder_point(summary, 14) == Quantity(210, "kg")
    assert not needs_ordering(summary, 14)
    assert needs_ordering(summary, 100)


def test_a_negative_lead_time_is_refused():
    summary = summarise_feed(FeedingLog(), FeedStore(), MARCH)
    with pytest.raises(ValidationError):
        reorder_point(summary, -1)


def test_the_share_of_a_month_that_went_to_one_lot():
    book = log(("2025-03-01", 75, LOT), ("2025-03-01", 25, "2024-CHK-02"))
    summary = summarise_feed(book, store(("FL-001", "1000", "2025-02-01")), MARCH)
    assert share_of_feed(summary, book, LOT) == Decimal("0.75")


def test_a_month_that_fed_nothing_has_no_share_to_report():
    summary = summarise_feed(FeedingLog(), FeedStore(), MARCH)
    with pytest.raises(ValidationError):
        share_of_feed(summary, FeedingLog(), LOT)
