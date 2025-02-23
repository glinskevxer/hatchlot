from decimal import Decimal

import pytest

from hatchlot.calendar import DateRange
from hatchlot.distribution.request import (
    RequestBook,
    RequestState,
    StockingRequest,
    fill_rate,
    total_biomass,
)
from hatchlot.errors import ValidationError
from hatchlot.quantities.base import Quantity

SPRING = DateRange("2025-04-01", "2025-05-31")


def request(code="SR-001", water="LAKE-A", fish="10000", grams="20", priority=5, window=SPRING):
    return StockingRequest(
        code=code,
        water=water,
        species="CHK",
        fish=Decimal(fish),
        target_weight=Quantity(grams, "g"),
        window=window,
        requested_by="district biologist",
        priority=priority,
    )


def test_a_request_normalises_its_codes_and_needs_a_requester():
    entry = request(code=" sr 001 ", water=" lake a ")
    assert entry.code == "SR-001"
    assert entry.water == "LAKE-A"
    assert entry.state is RequestState.OPEN
    with pytest.raises(ValidationError):
        StockingRequest(
            code="SR-1",
            water="LAKE-A",
            species="CHK",
            fish=Decimal(100),
            target_weight=Quantity(20, "g"),
            window=SPRING,
            requested_by="  ",
        )


def test_an_empty_request_or_an_impossible_priority_is_refused():
    with pytest.raises(ValidationError):
        request(fish="0")
    with pytest.raises(ValidationError):
        request(grams="0")
    with pytest.raises(ValidationError):
        request(priority=0)
    with pytest.raises(ValidationError):
        request(priority=10)


def test_a_size_tolerance_outside_a_share_is_refused():
    with pytest.raises(ValidationError):
        StockingRequest(
            code="SR-1",
            water="LAKE-A",
            species="CHK",
            fish=Decimal(100),
            target_weight=Quantity(20, "g"),
            window=SPRING,
            requested_by="biologist",
            size_tolerance=Decimal("1.5"),
        )


def test_what_a_request_will_take_in_size_and_in_date():
    entry = request(grams="20")
    assert entry.accepts_size(Quantity(20, "g"))
    assert entry.accepts_size(Quantity(24, "g"))
    assert not entry.accepts_size(Quantity(30, "g"))
    assert entry.accepts_day("2025-04-15")
    assert not entry.accepts_day("2025-06-15")
    with pytest.raises(ValidationError):
        entry.accepts_size(Quantity(0, "g"))


def test_a_delivery_comes_off_the_outstanding_count():
    entry = request(fish="10000")
    assert entry.deliver(4000, "2025-04-15") == Decimal(6000)
    assert entry.state is RequestState.PARTIAL
    assert entry.filled_share == Decimal("0.4")


def test_a_delivery_that_finishes_a_request_closes_it():
    entry = request(fish="1000")
    entry.deliver(1000, "2025-04-15")
    assert entry.state is RequestState.FILLED
    assert entry.outstanding == Decimal(0)


def test_a_delivery_over_the_outstanding_or_outside_the_window_is_refused():
    entry = request(fish="1000")
    with pytest.raises(ValidationError):
        entry.deliver(2000, "2025-04-15")
    with pytest.raises(ValidationError):
        entry.deliver(500, "2025-08-15")
    with pytest.raises(ValidationError):
        entry.deliver(0, "2025-04-15")


def test_nothing_is_delivered_against_a_closed_request():
    entry = request(fish="1000")
    entry.deliver(1000, "2025-04-15")
    with pytest.raises(ValidationError):
        entry.deliver(1, "2025-04-16")


def test_declining_a_request_needs_a_reason_and_closes_it():
    entry = request()
    entry.decline("no fish of that size this year")
    assert entry.state is RequestState.DECLINED
    assert entry.note.startswith("no fish")
    with pytest.raises(ValidationError):
        request().decline("  ")


def test_a_request_lapses_once_its_window_has_gone_by():
    entry = request()
    assert not entry.lapse("2025-05-01")
    assert entry.lapse("2025-06-01")
    assert entry.state is RequestState.LAPSED
    assert not entry.lapse("2025-07-01")


def test_what_a_request_weighs_at_its_target_size():
    assert request(fish="10000", grams="20").biomass() == Quantity("200.000", "kg")


def book(*requests):
    register = RequestBook()
    for entry in requests:
        register.add(entry)
    return register


def test_the_book_slices_by_species_water_and_window():
    register = book(
        request(code="SR-001", water="LAKE-A"),
        request(
            code="SR-002",
            water="LAKE-B",
            window=DateRange("2025-09-01", "2025-10-01"),
        ),
    )
    assert len(register.for_species("chinook")) == 2
    assert len(register.for_water("lake b")) == 1
    assert len(register.due_within(DateRange("2025-04-01", "2025-04-30"))) == 1


def test_the_open_requests_and_the_outstanding_fish():
    register = book(request(code="SR-001", fish="10000"), request(code="SR-002", fish="5000"))
    register.get("SR-001").deliver(4000, "2025-04-15")
    assert register.outstanding_fish() == Decimal(11000)
    register.get("SR-002").decline("no stock")
    assert len(register.open_requests()) == 1
    assert register.outstanding_fish() == Decimal(6000)
    assert register.outstanding_fish("CHK") == Decimal(6000)


def test_lapsing_the_book_says_what_it_closed():
    register = book(
        request(code="SR-001"),
        request(code="SR-002", window=DateRange("2025-09-01", "2025-10-01")),
    )
    assert register.lapse_all("2025-06-01") == ("SR-001",)
    assert register.lapse_all("2025-06-02") == ()


def test_the_book_orders_by_priority_then_by_window():
    register = book(
        request(code="SR-001", priority=5),
        request(code="SR-002", priority=1),
        request(code="SR-003", priority=1, window=DateRange("2025-03-01", "2025-03-31")),
    )
    assert [entry.code for entry in register.by_priority()] == ["SR-003", "SR-002", "SR-001"]


def test_the_biomass_and_the_fill_rate_across_a_set():
    entries = [request(code="SR-001", fish="10000"), request(code="SR-002", fish="10000")]
    entries[0].deliver(5000, "2025-04-15")
    assert total_biomass(entries) == Quantity("400.000", "kg")
    assert fill_rate(entries) == Decimal("0.25")


def test_the_fill_rate_of_nothing_is_refused():
    with pytest.raises(ValidationError):
        fill_rate([])
