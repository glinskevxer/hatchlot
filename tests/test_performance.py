"""Guards on the two things that grow with the size of a station.

Neither of these is a benchmark. They are ceilings, set well above what the code
does now and well below what it did before the journal grew its key index, so
they fail if somebody puts a scan back into a loop over lots.
"""

import time
from datetime import date, timedelta
from decimal import Decimal

from hatchlot.identifiers import LotCode
from hatchlot.quantities.base import Quantity
from hatchlot.rearing.container import Container, ContainerKind, ContainerRegister
from hatchlot.rearing.inventory import take_inventory
from hatchlot.rearing.ledger import EntryKind, Ledger, LedgerEntry
from hatchlot.rearing.lot import RearingLot

LOTS = 120
ENTRIES_PER_LOT = 12


def station():
    containers = ContainerRegister()
    containers.add(
        Container(
            code="RW-1",
            kind=ContainerKind.RACEWAY,
            length=Quantity(30, "m"),
            width=Quantity(3, "m"),
            depth=Quantity(1, "m"),
            flow=Quantity(500, "gpm"),
        )
    )
    lots = []
    ledger = Ledger()
    start = date(2025, 1, 15)
    for index in range(1, LOTS + 1):
        code = LotCode(2024, "CHK", index)
        lots.append(
            RearingLot(
                code=code,
                container="RW-1",
                ponded_on=start,
                population=Decimal(10000),
                mean_weight=Quantity("2.5", "g"),
            )
        )
        ledger.record(LedgerEntry(start, str(code), EntryKind.PONDED, 10000, "kt"))
        for step in range(1, ENTRIES_PER_LOT):
            ledger.record(
                LedgerEntry(
                    start + timedelta(days=step),
                    str(code),
                    EntryKind.MORTALITY,
                    1,
                    "kt",
                    "background loss",
                )
            )
    return lots, containers, ledger


def test_the_ledger_holds_what_was_put_in_it():
    lots, _, ledger = station()
    assert len(ledger) == LOTS * ENTRIES_PER_LOT
    assert len(ledger.lots()) == LOTS
    assert ledger.balance(str(lots[0].code)).closing == Decimal(10000 - (ENTRIES_PER_LOT - 1))


def test_a_lot_is_found_without_walking_the_whole_journal():
    lots, _, ledger = station()
    started = time.perf_counter()
    for lot in lots:
        assert len(ledger.for_lot(str(lot.code))) == ENTRIES_PER_LOT
    assert time.perf_counter() - started < 2.0


def test_an_inventory_over_a_station_of_lots_stays_quick():
    lots, containers, ledger = station()
    started = time.perf_counter()
    inventory = take_inventory(lots, containers, ledger, "2025-06-01")
    assert time.perf_counter() - started < 5.0
    assert len(inventory.positions) == LOTS


def test_every_lot_still_balances_against_its_own_entries():
    lots, _, ledger = station()
    for lot in lots:
        code = str(lot.code)
        balance = ledger.balance(code)
        assert balance.opened == Decimal(10000)
        assert balance.removed == Decimal(ENTRIES_PER_LOT - 1)


def test_the_key_index_and_the_full_list_agree():
    lots, _, ledger = station()
    for lot in lots[:5]:
        code = str(lot.code)
        by_index = ledger.for_lot(code)
        by_scan = tuple(entry for entry in ledger.all() if entry.lot == code)
        assert by_index == by_scan
