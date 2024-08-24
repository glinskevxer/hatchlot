from decimal import Decimal

import pytest

from hatchlot.errors import PolicyError, ValidationError
from hatchlot.numeric import quantize
from hatchlot.quantities.base import Quantity
from hatchlot.rearing.container import (
    Container,
    ContainerKind,
    ContainerRegister,
    exchange_ratio,
)


def raceway(code="RW-1", flow="500", length="30", width="3", depth="1", source="SP-1"):
    return Container(
        code=code,
        kind=ContainerKind.RACEWAY,
        length=Quantity(length, "m"),
        width=Quantity(width, "m"),
        depth=Quantity(depth, "m"),
        flow=Quantity(flow, "gpm"),
        water_source=source,
    )


def test_a_unit_normalises_its_code_and_its_source():
    unit = raceway(code=" rw 1 ", source=" sp 1 ")
    assert unit.code == "RW-1"
    assert unit.water_source == "SP-1"


def test_a_unit_with_no_dimension_or_no_flow_is_refused():
    with pytest.raises(ValidationError):
        raceway(length="0")
    with pytest.raises(ValidationError):
        raceway(depth="0")
    with pytest.raises(ValidationError):
        raceway(flow="0")


def test_a_kind_that_is_not_a_kind_is_refused():
    with pytest.raises(ValidationError):
        Container(
            code="RW-1",
            kind="raceway",  # type: ignore[arg-type]
            length=Quantity(1, "m"),
            width=Quantity(1, "m"),
            depth=Quantity(1, "m"),
            flow=Quantity(1, "gpm"),
        )


def test_the_volume_comes_off_the_dimensions():
    assert raceway().volume == Quantity(90, "m3")
    assert quantize(raceway().volume.to("ft3").amount, 1) == Decimal("3178.3")


def test_the_exchange_rate_and_the_turnover_are_two_views_of_one_number():
    unit = raceway(flow="500")
    assert quantize(unit.exchange_rate, 3) == Decimal("1.262")
    assert quantize(unit.turnover_minutes, 1) == Decimal("47.6")


def test_more_water_turns_a_unit_over_faster():
    slow = raceway(flow="250")
    fast = raceway(flow="1000")
    assert fast.turnover_minutes < slow.turnover_minutes
    assert fast.exchange_rate > slow.exchange_rate


def test_the_valve_makes_a_unit_on_a_different_flow():
    unit = raceway(flow="500").with_flow(Quantity(750, "gpm"))
    assert unit.flow == Quantity(750, "gpm")
    with pytest.raises(ValidationError):
        raceway().with_flow(Quantity(0, "gpm"))


def test_outdoor_and_self_cleaning_are_properties_of_the_kind():
    assert ContainerKind.RACEWAY.is_outdoor
    assert not ContainerKind.TANK.is_outdoor
    assert ContainerKind.CIRCULAR.is_self_cleaning
    assert not ContainerKind.RACEWAY.is_self_cleaning


def test_a_unit_out_of_service_refuses_work_by_name():
    unit = raceway()
    unit.check_available()
    unit.take_out_of_service("liner torn")
    assert not unit.is_available()
    with pytest.raises(PolicyError) as excinfo:
        unit.check_available()
    assert excinfo.value.rule == "container.out_of_service"
    unit.return_to_service()
    assert unit.is_available()


def test_taking_a_unit_off_needs_a_reason():
    with pytest.raises(ValidationError):
        raceway().take_out_of_service("  ")


def register_with(*units):
    register = ContainerRegister()
    for unit in units:
        register.add(unit)
    return register


def test_the_register_slices_by_kind_source_and_availability():
    tank = Container(
        code="TK-1",
        kind=ContainerKind.TANK,
        length=Quantity(3, "m"),
        width=Quantity(1, "m"),
        depth=Quantity(1, "m"),
        flow=Quantity(60, "gpm"),
        water_source="WL-1",
    )
    register = register_with(raceway(), tank)
    assert [unit.code for unit in register.of_kind(ContainerKind.TANK)] == ["TK-1"]
    assert [unit.code for unit in register.on_source("sp 1")] == ["RW-1"]
    register.get("RW-1").take_out_of_service("liner torn")
    assert [unit.code for unit in register.available()] == ["TK-1"]


def test_the_totals_across_a_station():
    register = register_with(raceway(code="RW-1"), raceway(code="RW-2"))
    assert register.total_volume() == Quantity(180, "m3")
    assert register.total_flow("gpm") == Quantity(1000, "gpm")
    register.get("RW-1").take_out_of_service("liner torn")
    assert register.total_flow("gpm") == Quantity(500, "gpm")


def test_the_slowest_unit_is_the_one_that_worries():
    register = register_with(raceway(code="RW-1", flow="500"), raceway(code="RW-2", flow="100"))
    slowest = register.slowest()
    assert slowest is not None
    assert slowest.code == "RW-2"
    assert ContainerRegister().slowest() is None


def test_how_much_more_water_a_target_turnover_needs():
    unit = raceway(flow="500")
    assert quantize(exchange_ratio(unit, 60), 3) == Decimal("0.793")
    assert exchange_ratio(unit, 30) > Decimal(1)
    with pytest.raises(ValidationError):
        exchange_ratio(unit, 0)
