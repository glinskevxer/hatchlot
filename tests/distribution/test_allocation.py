from decimal import Decimal

import pytest

from hatchlot.calendar import DateRange
from hatchlot.distribution.allocation import (
    AllocationPolicy,
    Offer,
    allocate,
    coverage,
    mean_size_gap,
    size_gap,
    suits,
)
from hatchlot.distribution.request import StockingRequest
from hatchlot.errors import ValidationError
from hatchlot.quantities.base import Quantity

SPRING = DateRange("2025-04-01", "2025-05-31")


def request(code="SR-001", fish="10000", grams="20", priority=5, species="CHK", window=SPRING):
    return StockingRequest(
        code=code,
        water=f"LAKE-{code[-1]}",
        species=species,
        fish=Decimal(fish),
        target_weight=Quantity(grams, "g"),
        window=window,
        requested_by="biologist",
        priority=priority,
    )


def offer(lot="2024-CHK-01", fish="10000", grams="20", ready="2025-04-01", species="CHK"):
    return Offer(lot, species, Decimal(fish), Quantity(grams, "g"), ready)


def test_an_offer_normalises_its_lot_and_resolves_its_species():
    entry = offer(lot=" 2024 chk 01 ", species="chinook")
    assert entry.lot == "2024-CHK-01"
    assert entry.species == "CHK"


def test_an_offer_of_nothing_is_refused():
    with pytest.raises(ValidationError):
        offer(fish="0")
    with pytest.raises(ValidationError):
        offer(grams="0")


def test_a_request_only_takes_the_right_species_size_and_timing():
    ask = request(grams="20")
    assert suits(ask, offer(grams="20"))
    assert not suits(ask, offer(species="COH"))
    assert not suits(ask, offer(grams="40"))
    assert not suits(ask, offer(ready="2025-07-01"))


def test_the_size_gap_is_a_share_of_what_was_asked_for():
    assert size_gap(request(grams="20"), offer(grams="24")) == Decimal("0.2")
    assert size_gap(request(grams="20"), offer(grams="20")) == Decimal(0)


def test_a_plan_with_no_requests_or_a_bad_policy_is_refused():
    with pytest.raises(ValidationError):
        allocate([], [offer()])
    with pytest.raises(ValidationError):
        allocate([request()], [offer()], "priority")  # type: ignore[arg-type]


def test_the_same_lot_offered_twice_is_refused():
    with pytest.raises(ValidationError):
        allocate([request()], [offer(), offer()])


def test_plenty_of_fish_fills_everything():
    plan = allocate([request(code="SR-001"), request(code="SR-002")], [offer(fish="50000")])
    assert plan.unfilled == ()
    assert plan.fish_allocated == Decimal(20000)
    assert plan.unused["2024-CHK-01"] == Decimal(30000)


def test_priority_fills_the_top_of_the_list_and_leaves_the_bottom_empty():
    plan = allocate(
        [request(code="SR-001", priority=1), request(code="SR-002", priority=9)],
        [offer(fish="10000")],
    )
    assert plan.for_request("SR-001")[0].fish == Decimal(10000)
    assert plan.unfilled == ("SR-002",)


def test_pro_rata_gives_everybody_a_share_instead():
    plan = allocate(
        [request(code="SR-001", priority=1), request(code="SR-002", priority=9)],
        [offer(fish="10000")],
        AllocationPolicy.PRO_RATA,
    )
    assert len(plan.for_request("SR-001")) == 1
    assert len(plan.for_request("SR-002")) == 1
    assert plan.unfilled == ()


def test_best_fit_puts_the_closest_size_in_each_water():
    plan = allocate(
        [request(code="SR-001", fish="1000", grams="20")],
        [
            offer(lot="2024-CHK-01", fish="1000", grams="24", ready="2025-04-01"),
            offer(lot="2024-CHK-02", fish="1000", grams="20", ready="2025-04-10"),
        ],
        AllocationPolicy.BEST_FIT,
    )
    assert plan.assignments[0].lot == "2024-CHK-02"
    assert plan.assignments[0].is_exact_size


def test_priority_takes_the_lot_that_is_ready_first():
    plan = allocate(
        [request(code="SR-001", fish="1000", grams="20")],
        [
            offer(lot="2024-CHK-01", fish="1000", grams="24", ready="2025-04-01"),
            offer(lot="2024-CHK-02", fish="1000", grams="20", ready="2025-04-10"),
        ],
    )
    assert plan.assignments[0].lot == "2024-CHK-01"


def test_one_request_can_be_filled_off_two_lots():
    plan = allocate(
        [request(code="SR-001", fish="15000")],
        [offer(lot="2024-CHK-01", fish="10000"), offer(lot="2024-CHK-02", fish="10000")],
    )
    assert len(plan.for_request("SR-001")) == 2
    assert plan.fish_allocated == Decimal(15000)


def test_a_request_nothing_suits_comes_back_unfilled():
    plan = allocate([request(grams="100")], [offer(grams="20")])
    assert plan.unfilled == ("SR-001",)
    assert plan.fish_allocated == Decimal(0)


def test_a_closed_request_is_left_out_of_the_allocation():
    closed = request(code="SR-002")
    closed.decline("no stock")
    plan = allocate([request(code="SR-001"), closed], [offer(fish="50000")])
    assert plan.unfilled == ()
    assert len(plan.assignments) == 1


def test_a_partly_delivered_request_is_only_allocated_its_remainder():
    ask = request(code="SR-001", fish="10000")
    ask.deliver(6000, "2025-04-15")
    plan = allocate([ask], [offer(fish="50000")])
    assert plan.fish_allocated == Decimal(4000)


def test_the_plan_can_be_asked_about_one_lot():
    plan = allocate(
        [request(code="SR-001", fish="5000"), request(code="SR-002", fish="5000")],
        [offer(fish="50000")],
    )
    assert len(plan.for_lot("2024-CHK-01")) == 2


def test_the_coverage_of_a_plan():
    asks = [request(code="SR-001", fish="10000"), request(code="SR-002", fish="10000")]
    plan = allocate(asks, [offer(fish="10000")])
    assert coverage(plan, asks) == Decimal("0.5")


def test_the_coverage_of_nothing_outstanding_is_refused():
    filled = request(code="SR-001", fish="1000")
    filled.deliver(1000, "2025-04-15")
    plan = allocate([request(code="SR-002")], [offer()])
    with pytest.raises(ValidationError):
        coverage(plan, [filled])


def test_the_mean_size_gap_of_a_plan():
    plan = allocate(
        [request(code="SR-001", fish="1000", grams="20")],
        [offer(fish="1000", grams="24")],
    )
    assert mean_size_gap(plan) == Decimal("0.2")


def test_a_plan_that_allocated_nothing_has_no_size_gap():
    plan = allocate([request(grams="100")], [offer(grams="20")])
    assert mean_size_gap(plan) == Decimal(0)


def test_the_line_says_the_policy_and_the_counts():
    plan = allocate([request()], [offer(fish="50000")])
    assert "priority" in plan.line()
    assert "1 assignments" in plan.line()
