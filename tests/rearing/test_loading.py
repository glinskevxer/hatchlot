from datetime import date
from decimal import Decimal

import pytest

from hatchlot.errors import PolicyError
from hatchlot.identifiers import LotCode
from hatchlot.quantities.base import Quantity
from hatchlot.quantities.temperature import Temperature
from hatchlot.rearing.container import Container, ContainerKind
from hatchlot.rearing.loading import (
    LoadingStatus,
    assess,
    check_loading,
    days_until_full,
    room_for,
)
from hatchlot.rearing.lot import RearingLot
from hatchlot.station import StationProfile
from hatchlot.water.capacity import BindingLimit


def container(flow="500", length="30", width="3", depth="1"):
    return Container(
        code="RW-1",
        kind=ContainerKind.RACEWAY,
        length=Quantity(length, "m"),
        width=Quantity(width, "m"),
        depth=Quantity(depth, "m"),
        flow=Quantity(flow, "gpm"),
    )


def lot(population="50000", grams="2.5", species="CHK"):
    return RearingLot(
        code=LotCode(2024, species, 1),
        container="RW-1",
        ponded_on=date(2025, 1, 15),
        population=Decimal(population),
        mean_weight=Quantity(grams, "g"),
    )


def test_a_lightly_stocked_raceway_is_fine():
    result = assess(container(), lot(population="10000"))
    assert result.status is LoadingStatus.OK
    assert not result.status.is_actionable
    assert result.headroom > Quantity(0, "lb")


def test_an_overloaded_raceway_reads_over_and_refuses_by_name():
    result = assess(container(flow="100"), lot(population="400000"))
    assert result.status is LoadingStatus.OVER
    with pytest.raises(PolicyError) as excinfo:
        check_loading(result)
    assert excinfo.value.rule.startswith("loading.")


def test_a_unit_inside_the_tolerance_reads_as_a_warning():
    unit = container()
    fish = lot(population="10000")
    baseline = assess(unit, fish)
    allowed = baseline.allowed.to("lb").amount
    each = fish.mean_weight.to("lb").amount
    population = (allowed * Decimal("0.98") / each).to_integral_value()
    result = assess(unit, lot(population=str(population)))
    assert result.status is LoadingStatus.WARNING
    assert result.status.is_actionable


def test_a_station_with_a_wider_tolerance_warns_sooner():
    unit = container()
    fish = lot(population="10000")
    allowed = assess(unit, fish).allowed.to("lb").amount
    each = fish.mean_weight.to("lb").amount
    population = (allowed * Decimal("0.8") / each).to_integral_value()
    loose = StationProfile(code="X", name="X", loading_tolerance=Decimal("0.3"))
    assert assess(unit, lot(population=str(population))).status is LoadingStatus.OK
    assert (
        assess(unit, lot(population=str(population)), profile=loose).status is LoadingStatus.WARNING
    )


def test_a_short_flow_makes_the_flow_index_bind():
    result = assess(container(flow="60"), lot(population="1000"))
    assert result.binding is BindingLimit.FLOW_INDEX


def test_a_small_box_on_plenty_of_water_makes_density_bind():
    result = assess(container(flow="2000", length="3"), lot(population="1000"))
    assert result.binding is BindingLimit.DENSITY_INDEX


def test_warm_water_with_a_high_floor_makes_oxygen_bind():
    result = assess(
        container(),
        lot(population="1000"),
        inflow_mgL="8.0",
        floor_mgL="7.0",
        temperature=Temperature(16, "C"),
    )
    assert result.binding is BindingLimit.OXYGEN


def test_two_species_are_not_allowed_the_same_loading():
    chinook = assess(container(), lot(population="1000", species="CHK"))
    trout = assess(container(), lot(population="1000", species="RBT"))
    assert trout.allowed > chinook.allowed


def test_the_line_says_the_share_and_the_limit_that_bound():
    line = assess(container(), lot(population="10000")).line()
    assert "RW-1/2024-CHK-01" in line
    assert "limit" in line


def test_how_many_more_fish_a_unit_would_take():
    result = assess(container(), lot(population="10000"))
    room = room_for(result, Quantity("2.5", "g"))
    assert room > Decimal(0)
    over = assess(container(flow="100"), lot(population="400000"))
    assert room_for(over, Quantity("2.5", "g")) == Decimal(0)


def test_how_long_before_growth_puts_a_unit_over():
    result = assess(container(), lot(population="10000"))
    days = days_until_full(result, "0.02")
    assert days is not None
    assert 1 < days < 365


def test_a_unit_already_over_or_not_growing_has_no_date():
    result = assess(container(), lot(population="10000"))
    assert days_until_full(result, 0) is None
    over = assess(container(flow="100"), lot(population="400000"))
    assert days_until_full(over, "0.02") is None


def test_growth_too_slow_to_matter_inside_the_horizon_has_no_date():
    result = assess(container(), lot(population="10000"))
    assert days_until_full(result, "0.00001", limit_days=30) is None
