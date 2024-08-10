from datetime import date
from decimal import Decimal

import pytest

from hatchlot.errors import PolicyError, StateError, ValidationError
from hatchlot.identifiers import LotCode
from hatchlot.incubation.eggslot import EggLot, EggStage, LossCause
from hatchlot.incubation.transfer import (
    Movement,
    MovementKind,
    movement_total,
    pond,
    split,
    transfer,
)
from hatchlot.incubation.vessel import Vessel, VesselKind, VesselRegister
from hatchlot.quantities.base import Quantity
from hatchlot.species import species

CHINOOK = species("CHK")
EYED = 500
SWUM = 1400


def lot(green="10000", stage=EggStage.EYED):
    return EggLot(
        code=LotCode(2024, "CHK", 1),
        take="T-001",
        species="CHK",
        spawned_on=date(2024, 9, 13),
        green_count=Decimal(green),
        stage=stage,
    )


def room():
    register = VesselRegister()
    for code in ("TR-1", "TR-2"):
        register.add(
            Vessel(
                code=code,
                kind=VesselKind.TRAY,
                flow=Quantity(20, "Lpm"),
                capacity_eggs=Decimal(12000),
            )
        )
    return register


def test_a_transfer_moves_eggs_and_leaves_the_lot_alone():
    register = room()
    eggs = lot()
    register.get("TR-1").load("2024-CHK-01", 10000)
    move = transfer(register, eggs, "2024-11-01", 4000, "TR-1", "TR-2", "kt", CHINOOK, EYED)
    assert register.get("TR-1").loaded == Decimal(6000)
    assert register.get("TR-2").loaded == Decimal(4000)
    assert eggs.count == Decimal(10000)
    assert move.kind is MovementKind.TRANSFER


def test_a_transfer_inside_the_tender_window_is_refused():
    register = room()
    register.get("TR-1").load("2024-CHK-01", 10000)
    with pytest.raises(PolicyError) as excinfo:
        transfer(register, lot(), "2024-10-01", 100, "TR-1", "TR-2", "kt", CHINOOK, 200)
    assert excinfo.value.rule == "incubation.tender"


def test_a_transfer_to_the_same_vessel_is_refused():
    register = room()
    register.get("TR-1").load("2024-CHK-01", 10000)
    with pytest.raises(ValidationError):
        transfer(register, lot(), "2024-11-01", 100, "TR-1", "TR-1", "kt", CHINOOK, EYED)


def test_a_closed_lot_does_not_move():
    register = room()
    with pytest.raises(StateError):
        transfer(
            register,
            lot(stage=EggStage.PONDED),
            "2024-11-01",
            100,
            "TR-1",
            "TR-2",
            "kt",
            CHINOOK,
            EYED,
        )


def test_a_movement_needs_a_person_and_a_real_count():
    with pytest.raises(ValidationError):
        Movement(
            day=date(2024, 11, 1),
            kind=MovementKind.TRANSFER,
            lot="2024-CHK-01",
            eggs=Decimal(100),
            origin="TR-1",
            destination="TR-2",
            moved_by=" ",
        )
    with pytest.raises(ValidationError):
        Movement(
            day=date(2024, 11, 1),
            kind=MovementKind.TRANSFER,
            lot="2024-CHK-01",
            eggs=Decimal(0),
            origin="TR-1",
            destination="TR-2",
            moved_by="kt",
        )


def test_a_split_makes_a_child_lot_off_what_it_was_given():
    parent = lot()
    child, move = split(parent, "2024-11-01", 4000, "A", "kt", CHINOOK, EYED)
    assert parent.count == Decimal(6000)
    assert child.green_count == Decimal(4000)
    assert child.count == Decimal(4000)
    assert child.stage is parent.stage
    assert move.kind is MovementKind.SPLIT
    assert move.destination == "2024-CHK-01A"


def test_the_split_comes_off_the_parent_as_handling():
    parent = lot()
    split(parent, "2024-11-01", 4000, "A", "kt", CHINOOK, EYED)
    assert parent.lost_to(LossCause.HANDLING) == Decimal(4000)


def test_a_split_that_leaves_nothing_is_refused():
    with pytest.raises(ValidationError):
        split(lot(green="1000"), "2024-11-01", 1000, "A", "kt", CHINOOK, EYED)


def test_a_split_inside_the_tender_window_is_refused():
    with pytest.raises(PolicyError):
        split(lot(), "2024-10-01", 100, "A", "kt", CHINOOK, 200)


def test_a_closed_lot_cannot_be_split():
    with pytest.raises(StateError):
        split(lot(stage=EggStage.PONDED), "2024-11-01", 100, "A", "kt", CHINOOK, EYED)


def test_ponding_empties_the_vessels_and_closes_the_lot():
    register = room()
    eggs = lot(stage=EggStage.HATCHED)
    register.get("TR-1").load("2024-CHK-01", 6000)
    register.get("TR-2").load("2024-CHK-01", 4000)
    move = pond(register, eggs, "2025-01-15", "RW-3", "kt", CHINOOK, SWUM)
    assert register.get("TR-1").is_empty
    assert register.get("TR-2").is_empty
    assert eggs.stage is EggStage.PONDED
    assert eggs.unit == "RW-3"
    assert move.eggs == Decimal(10000)


def test_a_lot_that_has_not_hatched_cannot_be_ponded():
    with pytest.raises(StateError):
        pond(room(), lot(stage=EggStage.EYED), "2025-01-15", "RW-3", "kt", CHINOOK, SWUM)


def test_a_lot_short_of_swim_up_cannot_be_ponded():
    with pytest.raises(ValidationError):
        pond(
            room(),
            lot(stage=EggStage.HATCHED),
            "2025-01-15",
            "RW-3",
            "kt",
            CHINOOK,
            900,
        )


def test_the_totals_by_kind_of_movement():
    parent = lot()
    _, first = split(parent, "2024-11-01", 2000, "A", "kt", CHINOOK, EYED)
    _, second = split(parent, "2024-11-02", 1000, "B", "kt", CHINOOK, EYED)
    assert movement_total([first, second], MovementKind.SPLIT) == Decimal(3000)
    assert movement_total([first, second], MovementKind.POND) == Decimal(0)
