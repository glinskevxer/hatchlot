from decimal import Decimal

import pytest

from hatchlot.errors import DuplicateError, PolicyError, ValidationError
from hatchlot.incubation.vessel import Vessel, VesselKind, VesselRegister
from hatchlot.quantities.base import Quantity


def tray(code="TR-1", capacity="12000", stack="", position=0):
    return Vessel(
        code=code,
        kind=VesselKind.TRAY,
        flow=Quantity(20, "Lpm"),
        capacity_eggs=Decimal(capacity),
        stack=stack,
        position=position,
    )


def jar(code="JR-1", litres="6"):
    return Vessel(
        code=code,
        kind=VesselKind.JAR,
        flow=Quantity(8, "Lpm"),
        volume=Quantity(litres, "L"),
    )


def test_a_tray_holds_a_number_and_a_jar_holds_a_volume():
    assert not VesselKind.TRAY.is_volumetric
    assert VesselKind.JAR.is_volumetric
    assert tray().capacity() == Decimal(12000)
    assert jar().capacity(2000) == Decimal(12000)


def test_a_jar_without_an_egg_size_cannot_say_what_it_holds():
    with pytest.raises(ValidationError):
        jar().capacity()


def test_a_tray_with_no_capacity_and_a_jar_with_no_volume_are_refused():
    with pytest.raises(ValidationError):
        tray(capacity="0")
    with pytest.raises(ValidationError):
        Vessel(code="JR-1", kind=VesselKind.JAR, flow=Quantity(8, "Lpm"))


def test_a_vessel_with_no_flow_or_no_kind_is_refused():
    with pytest.raises(ValidationError):
        Vessel(code="TR-1", kind=VesselKind.TRAY, flow=Quantity(0, "Lpm"), capacity_eggs=Decimal(1))
    with pytest.raises(ValidationError):
        Vessel(
            code="TR-1",
            kind="tray",  # type: ignore[arg-type]
            flow=Quantity(1, "Lpm"),
            capacity_eggs=Decimal(1),
        )


def test_a_tray_in_a_stack_needs_a_position():
    with pytest.raises(ValidationError):
        tray(stack="ST-1")
    assert tray(stack=" st 1 ", position=3).stack == "ST-1"


def test_loading_and_unloading_a_tray():
    unit = tray()
    unit.load("2024-CHK-01", 5000)
    assert unit.loaded == Decimal(5000)
    assert unit.free() == Decimal(7000)
    assert not unit.is_empty
    assert unit.unload("2024-CHK-01", 2000) == Decimal(2000)
    assert unit.loaded == Decimal(3000)
    assert unit.unload("2024-chk-01") == Decimal(3000)
    assert unit.is_empty


def test_two_lots_can_share_a_tray():
    unit = tray()
    unit.load("2024-CHK-01", 5000)
    unit.load("2024-CHK-02", 4000)
    assert unit.loaded == Decimal(9000)
    assert unit.fill_share() == Decimal("0.75")


def test_loading_the_same_lot_twice_adds_up():
    unit = tray()
    unit.load("2024-CHK-01", 2000)
    assert unit.load("2024-CHK-01", 3000) == Decimal(5000)


def test_an_overfill_is_refused_by_name():
    unit = tray(capacity="1000")
    with pytest.raises(PolicyError) as excinfo:
        unit.load("2024-CHK-01", 1200)
    assert excinfo.value.rule == "incubation.overfill"


def test_a_jar_is_filled_against_the_egg_size_it_was_given():
    unit = jar()
    unit.load("2024-CHK-01", 10000, 2000)
    assert unit.free(2000) == Decimal(2000)
    with pytest.raises(PolicyError):
        unit.load("2024-CHK-01", 3000, 2000)


def test_unloading_what_is_not_there_is_refused():
    unit = tray()
    with pytest.raises(ValidationError):
        unit.unload("2024-CHK-01")
    unit.load("2024-CHK-01", 1000)
    with pytest.raises(ValidationError):
        unit.unload("2024-CHK-01", 2000)


def test_loading_nothing_is_refused():
    with pytest.raises(ValidationError):
        tray().load("2024-CHK-01", 0)


def room(*vessels, stack_limit=8):
    register = VesselRegister(stack_limit=stack_limit)
    for vessel in vessels:
        register.add(vessel)
    return register


def test_a_stack_position_is_taken_once():
    register = room(tray(code="TR-1", stack="ST-1", position=1))
    with pytest.raises(DuplicateError):
        register.add(tray(code="TR-2", stack="ST-1", position=1))
    register.add(tray(code="TR-3", stack="ST-1", position=2))
    assert [v.code for v in register.in_stack("ST-1")] == ["TR-1", "TR-3"]


def test_a_stack_over_its_loaded_limit_is_refused_by_name():
    register = room(
        tray(code="TR-1", stack="ST-1", position=1),
        tray(code="TR-2", stack="ST-1", position=2),
        stack_limit=1,
    )
    register.get("TR-1").load("2024-CHK-01", 100)
    register.check_stack("ST-1")
    register.get("TR-2").load("2024-CHK-01", 100)
    assert register.loaded_in_stack("ST-1") == 2
    with pytest.raises(PolicyError) as excinfo:
        register.check_stack("ST-1")
    assert excinfo.value.rule == "incubation.stack_limit"


def test_a_stack_limit_below_one_is_refused():
    with pytest.raises(ValidationError):
        VesselRegister(stack_limit=0)
    assert VesselRegister().stack_limit == 8


def test_the_room_finds_where_a_lot_is_sitting():
    register = room(tray(code="TR-1"), tray(code="TR-2"), jar())
    register.get("TR-1").load("2024-CHK-01", 5000)
    register.get("TR-2").load("2024-CHK-01", 3000)
    register.get("JR-1").load("2024-CHK-02", 1000, 2000)
    assert [v.code for v in register.holding("2024-CHK-01")] == ["TR-1", "TR-2"]
    assert register.eggs_of("2024-CHK-01") == Decimal(8000)
    assert register.eggs_of("2024-CHK-09") == Decimal(0)


def test_the_room_lists_by_kind():
    register = room(tray(), jar())
    assert [v.code for v in register.of_kind(VesselKind.JAR)] == ["JR-1"]


def test_only_loaded_vessels_are_asking_for_water():
    register = room(tray(code="TR-1"), tray(code="TR-2"))
    assert register.flow_demand() == Quantity(0, "Lpm")
    register.get("TR-1").load("2024-CHK-01", 100)
    assert register.flow_demand() == Quantity(20, "Lpm")
