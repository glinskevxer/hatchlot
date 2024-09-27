from datetime import date
from decimal import Decimal

import pytest

from hatchlot.errors import PolicyError, StateError, ValidationError
from hatchlot.identifiers import LotCode
from hatchlot.quantities.base import Quantity
from hatchlot.rearing.container import Container, ContainerKind
from hatchlot.rearing.ledger import EntryKind, Ledger
from hatchlot.rearing.lot import RearingLot
from hatchlot.rearing.movement import (
    blended_weight,
    evens_out,
    merge_lots,
    move_container,
    split_lot,
)


def container(code="RW-1"):
    return Container(
        code=code,
        kind=ContainerKind.RACEWAY,
        length=Quantity(30, "m"),
        width=Quantity(3, "m"),
        depth=Quantity(1, "m"),
        flow=Quantity(500, "gpm"),
    )


def lot(sequence=1, population="50000", grams="2.5", unit="RW-1", species="CHK"):
    return RearingLot(
        code=LotCode(2024, species, sequence),
        container=unit,
        ponded_on=date(2025, 1, 15),
        population=Decimal(population),
        mean_weight=Quantity(grams, "g"),
    )


def test_moving_a_whole_lot_changes_the_unit_and_no_counts():
    fish = lot()
    move = move_container(fish, container("RW-2"), "2025-03-01", "kt")
    assert fish.container == "RW-2"
    assert fish.population == Decimal(50000)
    assert move.origin == "RW-1"


def test_moving_a_lot_into_the_unit_it_is_already_in_is_refused():
    with pytest.raises(ValidationError):
        move_container(lot(), container("RW-1"), "2025-03-01", "kt")


def test_moving_needs_a_person_and_an_available_unit():
    with pytest.raises(ValidationError):
        move_container(lot(), container("RW-2"), "2025-03-01", " ")
    unit = container("RW-2")
    unit.take_out_of_service("liner torn")
    with pytest.raises(PolicyError):
        move_container(lot(), unit, "2025-03-01", "kt")


def test_a_held_lot_does_not_move_and_says_why():
    fish = lot()
    fish.hold("treatment withdrawal")
    with pytest.raises(PolicyError) as excinfo:
        move_container(fish, container("RW-2"), "2025-03-01", "kt")
    assert excinfo.value.rule == "movement.held"


def test_a_closed_lot_does_not_move():
    fish = lot(population="100")
    fish.remove(100)
    with pytest.raises(StateError):
        move_container(fish, container("RW-2"), "2025-03-01", "kt")


def test_a_split_writes_both_sides_to_the_ledger():
    fish = lot(population="50000")
    ledger = Ledger()
    child, move = split_lot(fish, container("RW-2"), ledger, "2025-03-01", 20000, "A", "kt")
    assert fish.population == Decimal(30000)
    assert child.population == Decimal(20000)
    assert child.container == "RW-2"
    assert move.destination == "RW-2"
    kinds = [entry.kind for entry in ledger.for_lot("2024-CHK-01")]
    assert EntryKind.TRANSFER_OUT in kinds


def test_the_child_of_a_split_keeps_the_mean_weight_and_the_ponding_date():
    fish = lot(grams="3")
    child, _ = split_lot(fish, container("RW-2"), Ledger(), "2025-03-01", 100, "A", "kt")
    assert child.mean_weight == Quantity(3, "g")
    assert child.ponded_on == fish.ponded_on


def test_a_split_that_leaves_nothing_is_refused():
    with pytest.raises(ValidationError):
        split_lot(lot(population="100"), container("RW-2"), Ledger(), "2025-03-01", 100, "A", "kt")


def test_a_split_needs_a_person_and_fish():
    fish = lot()
    with pytest.raises(ValidationError):
        split_lot(fish, container("RW-2"), Ledger(), "2025-03-01", 0, "A", "kt")
    with pytest.raises(ValidationError):
        split_lot(fish, container("RW-2"), Ledger(), "2025-03-01", 100, "A", " ")


def test_merging_keeps_the_larger_lot_and_closes_the_smaller():
    keep = lot(1, population="40000", grams="2")
    absorb = lot(2, population="10000", grams="4", unit="RW-2")
    ledger = Ledger()
    move = merge_lots(keep, absorb, ledger, "2025-03-01", "kt")
    assert keep.population == Decimal(50000)
    assert keep.mean_weight == Quantity("2.4", "g")
    assert absorb.population == Decimal(0)
    assert absorb.state.is_closed
    assert "merged into" in absorb.note
    assert move.origin == "RW-2"


def test_merging_writes_both_sides():
    keep = lot(1, population="40000")
    absorb = lot(2, population="10000", unit="RW-2")
    ledger = Ledger()
    merge_lots(keep, absorb, ledger, "2025-03-01", "kt")
    assert ledger.balance("2024-CHK-01").closing == Decimal(10000)
    assert len(ledger.for_lot("2024-CHK-02")) == 1


def test_merging_the_wrong_way_round_is_refused():
    keep = lot(1, population="1000")
    absorb = lot(2, population="40000", unit="RW-2")
    with pytest.raises(ValidationError):
        merge_lots(keep, absorb, Ledger(), "2025-03-01", "kt")


def test_merging_two_species_is_refused_by_name():
    keep = lot(1, population="40000", species="CHK")
    absorb = lot(2, population="1000", species="COH", unit="RW-2")
    with pytest.raises(PolicyError) as excinfo:
        merge_lots(keep, absorb, Ledger(), "2025-03-01", "kt")
    assert excinfo.value.rule == "movement.species"


def test_a_lot_cannot_be_merged_into_itself():
    fish = lot()
    with pytest.raises(ValidationError):
        merge_lots(fish, fish, Ledger(), "2025-03-01", "kt")


def test_what_the_mean_weight_would_be_after_a_merge():
    first = lot(1, population="1000", grams="2")
    second = lot(2, population="1000", grams="4")
    assert blended_weight(first, second) == Quantity(3, "g")


def test_how_far_apart_two_lots_are_in_size():
    first = lot(1, grams="2")
    second = lot(2, grams="4")
    assert evens_out(first, second) == Decimal("0.5")
    assert evens_out(first, lot(3, grams="2")) == Decimal(0)
