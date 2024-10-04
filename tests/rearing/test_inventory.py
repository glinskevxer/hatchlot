from datetime import date
from decimal import Decimal

import pytest

from hatchlot.errors import ValidationError
from hatchlot.identifiers import LotCode
from hatchlot.quantities.base import Quantity
from hatchlot.rearing.container import Container, ContainerKind, ContainerRegister
from hatchlot.rearing.inventory import (
    average_density,
    biomass_by_container,
    station_use,
    take_inventory,
)
from hatchlot.rearing.ledger import EntryKind, Ledger, LedgerEntry
from hatchlot.rearing.loading import LoadingStatus
from hatchlot.rearing.lot import RearingLot


def containers(*codes, flow="500"):
    register = ContainerRegister()
    for code in codes:
        register.add(
            Container(
                code=code,
                kind=ContainerKind.RACEWAY,
                length=Quantity(30, "m"),
                width=Quantity(3, "m"),
                depth=Quantity(1, "m"),
                flow=Quantity(flow, "gpm"),
            )
        )
    return register


def lot(sequence=1, population="10000", grams="2.5", unit="RW-1"):
    return RearingLot(
        code=LotCode(2024, "CHK", sequence),
        container=unit,
        ponded_on=date(2025, 1, 15),
        population=Decimal(population),
        mean_weight=Quantity(grams, "g"),
    )


def ledger_for(*pairs):
    book = Ledger()
    for code, count in pairs:
        book.record(LedgerEntry("2025-01-15", code, EntryKind.PONDED, count, "kt"))
    return book


def test_an_inventory_that_agrees_everywhere_is_clean():
    inventory = take_inventory(
        [lot()], containers("RW-1"), ledger_for(("2024-CHK-01", 10000)), "2025-03-01"
    )
    assert inventory.is_clean
    assert inventory.population == Decimal(10000)
    assert inventory.biomass == Quantity("25.0000", "kg")


def test_a_lot_off_its_ledger_is_reported():
    inventory = take_inventory(
        [lot()], containers("RW-1"), ledger_for(("2024-CHK-01", 9000)), "2025-03-01"
    )
    assert not inventory.is_clean
    assert len(inventory.disagreeing) == 1
    assert inventory.disagreeing[0].ledger_difference == Decimal(1000)


def test_a_lot_in_a_unit_the_station_does_not_have_is_homeless():
    inventory = take_inventory(
        [lot(unit="RW-9")],
        containers("RW-1"),
        ledger_for(("2024-CHK-01", 10000)),
        "2025-03-01",
    )
    assert inventory.homeless == ("2024-CHK-01",)
    assert inventory.positions[0].loading is None
    assert inventory.positions[0].status is LoadingStatus.OK


def test_an_overloaded_unit_is_reported():
    inventory = take_inventory(
        [lot(population="400000")],
        containers("RW-1", flow="100"),
        ledger_for(("2024-CHK-01", 400000)),
        "2025-03-01",
    )
    assert len(inventory.overloaded) == 1
    assert not inventory.is_clean


def test_closed_lots_are_left_off_the_inventory():
    gone = lot(2, population="100")
    gone.remove(100)
    inventory = take_inventory(
        [lot(), gone], containers("RW-1"), ledger_for(("2024-CHK-01", 10000)), "2025-03-01"
    )
    assert len(inventory.positions) == 1


def test_the_same_lot_twice_is_refused():
    with pytest.raises(ValidationError):
        take_inventory([lot(), lot()], containers("RW-1"), Ledger(), "2025-03-01")


def test_the_inventory_can_be_asked_about_one_unit():
    inventory = take_inventory(
        [lot(1), lot(2, unit="RW-2")],
        containers("RW-1", "RW-2"),
        ledger_for(("2024-CHK-01", 10000), ("2024-CHK-02", 10000)),
        "2025-03-01",
    )
    assert len(inventory.for_container("rw 1")) == 1
    assert len(inventory.for_container("RW-9")) == 0


def test_the_ledger_is_read_as_of_the_inventory_day():
    book = ledger_for(("2024-CHK-01", 10000))
    book.record(LedgerEntry("2025-06-01", "2024-CHK-01", EntryKind.TRANSFER_IN, 5000, "kt"))
    early = take_inventory([lot()], containers("RW-1"), book, "2025-03-01")
    assert early.positions[0].ledger_population == Decimal(10000)


def test_two_lots_in_one_unit_add_up():
    inventory = take_inventory(
        [lot(1), lot(2)],
        containers("RW-1"),
        ledger_for(("2024-CHK-01", 10000), ("2024-CHK-02", 10000)),
        "2025-03-01",
    )
    assert biomass_by_container(inventory)["RW-1"] == Quantity("50.0000", "kg")


def test_the_share_of_the_station_in_use():
    inventory = take_inventory(
        [lot()], containers("RW-1", "RW-2"), ledger_for(("2024-CHK-01", 10000)), "2025-03-01"
    )
    assert station_use(inventory, containers("RW-1", "RW-2")) == Decimal("0.5")


def test_a_station_with_no_volume_has_no_share():
    inventory = take_inventory([], ContainerRegister(), Ledger(), "2025-03-01")
    with pytest.raises(ValidationError):
        station_use(inventory, ContainerRegister())


def test_the_average_density_across_the_units_in_use():
    register = containers("RW-1", "RW-2")
    inventory = take_inventory([lot()], register, ledger_for(("2024-CHK-01", 10000)), "2025-03-01")
    assert average_density(inventory, register).quantize(Decimal("0.0001")) == Decimal("0.2778")


def test_an_empty_station_has_no_density():
    register = containers("RW-1")
    inventory = take_inventory([], register, Ledger(), "2025-03-01")
    assert average_density(inventory, register) == Decimal(0)


def test_the_line_reads_like_a_morning_report():
    inventory = take_inventory(
        [lot()], containers("RW-1"), ledger_for(("2024-CHK-01", 9000)), "2025-03-01"
    )
    line = inventory.line()
    assert "1 lots" in line
    assert "1 off the ledger" in line
