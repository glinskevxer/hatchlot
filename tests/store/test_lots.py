from datetime import date
from decimal import Decimal

import pytest

from hatchlot.calendar import DateRange
from hatchlot.errors import NotFoundError, ValidationError
from hatchlot.identifiers import LotCode
from hatchlot.quantities.base import Quantity
from hatchlot.rearing.ledger import EntryKind, Ledger, LedgerEntry
from hatchlot.rearing.lot import LotState, RearingLot
from hatchlot.store.db import connect, execute
from hatchlot.store.lots import (
    ledger_balance,
    load_ledger,
    load_lot,
    load_lots,
    lot_population,
    save_entry,
    save_ledger,
    save_lot,
)
from hatchlot.store.migrations import migrate
from hatchlot.store.schema import ALL


def database(*containers):
    connection = connect()
    migrate(connection, ALL)
    for code in containers or ("RW-1",):
        execute(
            connection,
            "INSERT INTO container (code, kind, length_m, width_m, depth_m, flow_gpm) "
            f"VALUES ('{code}', 'raceway', '30', '3', '1', '500')",
        )
    return connection


def lot(sequence=1, container="RW-1", population="50000", grams="2.5"):
    return RearingLot(
        code=LotCode(2024, "CHK", sequence),
        container=container,
        ponded_on=date(2025, 1, 15),
        population=Decimal(population),
        mean_weight=Quantity(grams, "g"),
    )


def entry(day="2025-01-15", kind=EntryKind.PONDED, count=50000, lot_code="2024-CHK-01"):
    reason = "recount" if kind.needs_a_reason else ""
    return LedgerEntry(day, lot_code, kind, count, "kt", reason)


def test_a_lot_round_trips():
    connection = database()
    save_lot(connection, lot())
    back = load_lot(connection, "2024-CHK-01")
    assert back.population == Decimal(50000)
    assert back.mean_weight == Quantity("2.5", "g")
    assert back.container == "RW-1"
    assert back.state is LotState.REARING
    assert back.code.species == "CHK"


def test_saving_a_lot_twice_replaces_it():
    connection = database()
    save_lot(connection, lot(population="50000"))
    save_lot(connection, lot(population="48000"))
    assert load_lot(connection, "2024-CHK-01").population == Decimal(48000)


def test_a_lot_that_is_not_there_raises_not_found():
    with pytest.raises(NotFoundError):
        load_lot(database(), "2024-CHK-09")


def test_the_lots_come_back_in_code_order():
    connection = database("RW-1", "RW-2")
    save_lot(connection, lot(2, container="RW-2"))
    save_lot(connection, lot(1))
    assert [str(entry.code) for entry in load_lots(connection)] == [
        "2024-CHK-01",
        "2024-CHK-02",
    ]


def test_the_lots_can_be_narrowed_to_one_unit():
    connection = database("RW-1", "RW-2")
    save_lot(connection, lot(1, container="RW-1"))
    save_lot(connection, lot(2, container="RW-2"))
    assert len(load_lots(connection, container="rw 2")) == 1


def test_the_closed_lots_can_be_left_out():
    connection = database()
    save_lot(connection, lot(1))
    gone = lot(2, population="100")
    gone.remove(100)
    save_lot(connection, gone)
    assert len(load_lots(connection)) == 2
    assert len(load_lots(connection, live_only=True)) == 1


def test_a_lot_that_came_from_an_egg_lot_remembers_it():
    connection = database()
    entry_lot = lot()
    entry_lot.origin_egg_lot = "2024-CHK-01"
    save_lot(connection, entry_lot)
    assert load_lot(connection, "2024-CHK-01").origin_egg_lot == "2024-CHK-01"


def test_a_ledger_entry_round_trips():
    connection = database()
    save_entry(connection, entry())
    book = load_ledger(connection)
    assert len(book) == 1
    assert book.balance("2024-CHK-01").closing == Decimal(50000)


def test_the_ledger_can_be_narrowed_to_one_lot_or_one_window():
    connection = database()
    save_entry(connection, entry())
    save_entry(connection, entry(lot_code="2024-CHK-02"))
    save_entry(connection, entry(day="2025-06-01", kind=EntryKind.SAMPLE, count=100))
    assert len(load_ledger(connection, lot="2024-CHK-01")) == 2
    assert len(load_ledger(connection, window=DateRange("2025-01-01", "2025-01-31"))) == 2


def test_a_whole_ledger_saves_and_comes_back():
    connection = database()
    book = Ledger()
    book.record(entry())
    book.record(entry(day="2025-02-01", kind=EntryKind.MORTALITY, count=500))
    assert save_ledger(connection, book) == 2
    assert len(load_ledger(connection)) == 2


def test_saving_the_same_ledger_twice_is_refused():
    connection = database()
    book = Ledger()
    book.record(entry())
    save_ledger(connection, book)
    with pytest.raises(ValidationError):
        save_ledger(connection, book)


def test_an_adjustment_keeps_its_reason_through_the_database():
    connection = database()
    save_entry(connection, entry(kind=EntryKind.ADJUSTMENT, count=48000))
    stored = load_ledger(connection).all()[0]
    assert stored.kind is EntryKind.ADJUSTMENT
    assert stored.reason == "recount"


def test_a_transfer_keeps_its_counterparty():
    connection = database()
    save_entry(
        connection,
        LedgerEntry("2025-02-01", "2024-CHK-01", EntryKind.TRANSFER_OUT, 500, "kt", "", "RW-2"),
    )
    assert load_ledger(connection).all()[0].counterparty == "RW-2"


def test_the_lot_record_and_the_ledger_are_two_separate_answers():
    connection = database()
    save_lot(connection, lot(population="50000"))
    save_entry(connection, entry(count=48000))
    assert lot_population(connection, "2024-CHK-01") == Decimal(50000)
    assert ledger_balance(connection, "2024-CHK-01") == Decimal(48000)
