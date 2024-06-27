from decimal import Decimal

import pytest

from hatchlot.errors import ValidationError
from hatchlot.quantities.base import Quantity
from hatchlot.water.budget import AllocationPolicy, Demand, allocate


def demand(code, requested, minimum, priority=5):
    return Demand(
        container=code,
        requested=Quantity(requested, "gpm"),
        minimum=Quantity(minimum, "gpm"),
        priority=priority,
    )


DEMANDS = [
    demand("RW-1", 400, 200, priority=1),
    demand("RW-2", 400, 200, priority=5),
    demand("RW-3", 200, 100, priority=9),
]


def test_a_demand_normalises_its_unit_code():
    assert demand(" rw 1 ", 100, 50).container == "RW-1"


def test_a_minimum_above_the_request_is_refused():
    with pytest.raises(ValidationError):
        demand("RW-1", 100, 200)


def test_a_negative_request_is_refused():
    with pytest.raises(ValidationError):
        demand("RW-1", -1, 0)


@pytest.mark.parametrize("priority", [0, 10])
def test_a_priority_off_the_scale_is_refused(priority):
    with pytest.raises(ValidationError):
        demand("RW-1", 100, 50, priority=priority)


def test_a_plan_with_no_demands_is_refused():
    with pytest.raises(ValidationError):
        allocate(Quantity(1000, "gpm"), [])


def test_a_unit_cannot_ask_twice_in_one_plan():
    with pytest.raises(ValidationError):
        allocate(Quantity(1000, "gpm"), [demand("RW-1", 100, 50), demand("rw 1", 100, 50)])


def test_plenty_of_water_satisfies_everybody_under_every_policy():
    for policy in AllocationPolicy:
        plan = allocate(Quantity(2000, "gpm"), DEMANDS, policy)
        assert all(grant.is_satisfied for grant in plan.grants)
        assert plan.unallocated == Quantity(1000, "gpm")
        assert plan.starved == ()


def test_priority_order_starves_the_bottom_of_the_list():
    plan = allocate(Quantity(600, "gpm"), DEMANDS, AllocationPolicy.PRIORITY_FIRST)
    assert plan.for_container("RW-1").granted == Quantity(400, "gpm")
    assert plan.for_container("RW-2").granted == Quantity(200, "gpm")
    assert plan.for_container("RW-3").granted == Quantity(0, "gpm")
    assert [grant.container for grant in plan.starved] == ["RW-3"]


def test_pro_rata_leaves_everybody_the_same_fraction_short():
    plan = allocate(Quantity(500, "gpm"), DEMANDS, AllocationPolicy.PRO_RATA)
    assert plan.for_container("RW-1").granted == Quantity(200, "gpm")
    assert plan.for_container("RW-2").granted == Quantity(200, "gpm")
    assert plan.for_container("RW-3").granted == Quantity(100, "gpm")
    assert plan.starved == ()


def test_pro_rata_can_put_a_unit_under_its_minimum():
    plan = allocate(Quantity(400, "gpm"), DEMANDS, AllocationPolicy.PRO_RATA)
    assert len(plan.starved) == 3


def test_minimums_first_protects_every_unit_before_anybody_gets_extra():
    plan = allocate(Quantity(500, "gpm"), DEMANDS, AllocationPolicy.MINIMUM_FIRST)
    assert plan.starved == ()
    assert plan.for_container("RW-1").granted == Quantity(200, "gpm")
    assert plan.granted_total == Quantity(500, "gpm")


def test_water_left_over_after_the_minimums_goes_out_pro_rata_on_what_is_left():
    plan = allocate(Quantity(600, "gpm"), DEMANDS, AllocationPolicy.MINIMUM_FIRST)
    assert plan.for_container("RW-1").granted == Quantity(240, "gpm")
    assert plan.granted_total == Quantity(600, "gpm")


def test_minimums_first_still_runs_out_when_the_minimums_do_not_fit():
    plan = allocate(Quantity(300, "gpm"), DEMANDS, AllocationPolicy.MINIMUM_FIRST)
    assert plan.for_container("RW-1").granted == Quantity(200, "gpm")
    assert plan.for_container("RW-2").granted == Quantity(100, "gpm")
    assert plan.for_container("RW-3").granted == Quantity(0, "gpm")
    assert len(plan.starved) == 2


def test_the_extra_above_the_minimums_is_shared_by_what_is_still_wanted():
    plan = allocate(Quantity(700, "gpm"), DEMANDS, AllocationPolicy.MINIMUM_FIRST)
    assert plan.for_container("RW-1").granted == Quantity(280, "gpm")
    assert plan.for_container("RW-3").granted == Quantity(140, "gpm")


def test_the_shortfall_is_the_gap_from_what_was_asked_for():
    plan = allocate(Quantity(600, "gpm"), DEMANDS, AllocationPolicy.PRIORITY_FIRST)
    assert plan.for_container("RW-2").shortfall == Quantity(200, "gpm")
    assert plan.for_container("RW-1").shortfall == Quantity(0, "gpm")


def test_no_water_at_all_grants_nothing():
    plan = allocate(Quantity(0, "gpm"), DEMANDS, AllocationPolicy.MINIMUM_FIRST)
    assert plan.granted_total == Quantity(0, "gpm")
    assert len(plan.starved) == 3


def test_a_plan_of_units_that_want_nothing_grants_nothing():
    plan = allocate(
        Quantity(500, "gpm"),
        [demand("RW-1", 0, 0), demand("RW-2", 0, 0)],
        AllocationPolicy.PRO_RATA,
    )
    assert plan.granted_total == Quantity(0, "gpm")
    assert plan.unallocated == Quantity(500, "gpm")


def test_a_plan_of_units_already_at_their_minimum_hands_out_no_extra():
    plan = allocate(
        Quantity(500, "gpm"),
        [demand("RW-1", 200, 200), demand("RW-2", 200, 200)],
        AllocationPolicy.MINIMUM_FIRST,
    )
    assert plan.granted_total == Quantity(400, "gpm")
    assert plan.unallocated == Quantity(100, "gpm")


def test_asking_a_plan_about_a_unit_that_is_not_in_it():
    plan = allocate(Quantity(600, "gpm"), DEMANDS)
    with pytest.raises(ValidationError):
        plan.for_container("RW-9")


def test_a_supply_in_metric_is_lined_up_before_it_is_divided():
    plan = allocate(Quantity("2271.2471", "Lpm"), DEMANDS, AllocationPolicy.PRIORITY_FIRST)
    assert plan.for_container("RW-1").granted.rounded(0).amount == Decimal(400)
