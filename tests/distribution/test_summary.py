from datetime import date
from decimal import Decimal

import pytest

from hatchlot.calendar import DateRange
from hatchlot.distribution import (
    Release,
    ReleaseKind,
    ReleaseRegister,
    RequestBook,
    StockingRequest,
    summarise_distribution,
)
from hatchlot.distribution.summary import (
    biggest_shortfall,
    by_lot,
    by_water,
    cost_per_fish,
    release_share,
)
from hatchlot.errors import ValidationError
from hatchlot.quantities.base import Quantity

SPRING = DateRange("2025-04-01", "2025-05-31")


def request(code="SR-001", water="LAKE-A", fish="10000"):
    return StockingRequest(
        code=code,
        water=water,
        species="CHK",
        fish=Decimal(fish),
        target_weight=Quantity(20, "g"),
        window=SPRING,
        requested_by="biologist",
    )


def book(*requests):
    register = RequestBook()
    for entry in requests:
        register.add(entry)
    return register


def release(
    code="RL-001",
    water="LAKE-A",
    lot="2024-CHK-01",
    fish="10000",
    day="2025-04-15",
    kind=ReleaseKind.DIRECT,
):
    return Release(
        code=code,
        day=date.fromisoformat(day),
        lot=lot,
        water=water,
        request="SR-001",
        fish=Decimal(fish),
        mean_weight=Quantity(20, "g"),
        kind=kind,
        released_by="kt",
    )


def register_of(*releases):
    register = ReleaseRegister()
    for entry in releases:
        register.record(entry)
    return register


def test_a_season_reads_both_sides():
    asked = request(fish="20000")
    asked.deliver(10000, "2025-04-15")
    summary = summarise_distribution(book(asked), register_of(release()), SPRING)
    assert summary.requests == 1
    assert summary.partial == 1
    assert summary.fish_requested == Decimal(20000)
    assert summary.fish_released == Decimal(10000)
    assert summary.fill_rate == Decimal("0.5")
    assert summary.unmet == Decimal(10000)


def test_requests_outside_the_window_are_left_out():
    away = request(code="SR-002")
    away.window = DateRange("2025-09-01", "2025-10-01")
    summary = summarise_distribution(book(request(), away), ReleaseRegister(), SPRING)
    assert summary.requests == 1


def test_a_transfer_is_not_counted_as_a_release():
    summary = summarise_distribution(
        book(request()),
        register_of(release(kind=ReleaseKind.TRANSFER)),
        SPRING,
    )
    assert summary.fish_released == Decimal(0)
    assert summary.waters == ()


def test_the_states_are_counted_separately():
    filled = request(code="SR-001", fish="1000")
    filled.deliver(1000, "2025-04-15")
    declined = request(code="SR-002")
    declined.decline("no stock")
    lapsed = request(code="SR-003")
    lapsed.lapse("2025-06-05")
    summary = summarise_distribution(book(filled, declined, lapsed), ReleaseRegister(), SPRING)
    assert summary.filled == 1
    assert summary.declined == 1
    assert summary.lapsed == 1
    assert summary.closed_without_fish == 2


def test_a_season_with_no_requests_has_no_fill_rate_to_report():
    summary = summarise_distribution(RequestBook(), ReleaseRegister(), SPRING)
    assert summary.fill_rate == Decimal(0)
    assert summary.unmet == Decimal(0)


def test_the_biomass_and_the_waters_of_a_season():
    summary = summarise_distribution(
        book(request()),
        register_of(release(), release(code="RL-002", water="LAKE-B", fish="5000")),
        SPRING,
    )
    assert summary.biomass_released == Quantity("300.000", "kg")
    assert summary.waters == ("LAKE-A", "LAKE-B")


def test_the_split_by_water_and_by_lot():
    register = register_of(
        release(code="RL-001", water="LAKE-A", lot="2024-CHK-01", fish="10000"),
        release(code="RL-002", water="LAKE-B", lot="2024-CHK-01", fish="5000"),
        release(code="RL-003", water="LAKE-A", lot="2024-CHK-02", fish="2000"),
    )
    assert by_water(register, SPRING) == {"LAKE-A": Decimal(12000), "LAKE-B": Decimal(5000)}
    assert by_lot(register, SPRING)["2024-CHK-01"] == Decimal(15000)


def test_the_open_request_furthest_from_being_filled():
    small = request(code="SR-001", fish="1000")
    big = request(code="SR-002", fish="50000")
    assert biggest_shortfall(book(small, big)) == "SR-002"
    assert biggest_shortfall(RequestBook()) is None


def test_a_book_with_everything_filled_has_no_shortfall_to_report():
    filled = request(code="SR-001", fish="1000")
    filled.deliver(1000, "2025-04-15")
    assert biggest_shortfall(book(filled)) is None


def test_what_each_fish_cost():
    assert cost_per_fish(20000, 10000) == Decimal(2)
    with pytest.raises(ValidationError):
        cost_per_fish(20000, 0)
    with pytest.raises(ValidationError):
        cost_per_fish(0, 10000)


def test_the_share_of_a_season_that_went_into_one_water():
    register = register_of(
        release(code="RL-001", water="LAKE-A", fish="7500"),
        release(code="RL-002", water="LAKE-B", fish="2500"),
    )
    summary = summarise_distribution(book(request()), register, SPRING)
    assert release_share(summary, "lake a", register) == Decimal("0.75")
    assert release_share(summary, "LAKE-C", register) == Decimal(0)


def test_a_season_that_released_nothing_has_no_share_to_report():
    summary = summarise_distribution(book(request()), ReleaseRegister(), SPRING)
    with pytest.raises(ValidationError):
        release_share(summary, "LAKE-A", ReleaseRegister())


def test_the_line_reads_like_a_season_heading():
    asked = request(fish="20000")
    summary = summarise_distribution(book(asked), register_of(release()), SPRING)
    assert "10000 of 20000 fish" in summary.line()
