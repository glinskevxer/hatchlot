"""The database, opened and closed the way a season actually uses it.

Nothing here is a new rule. What it checks is that the schema, the repositories
and the session hold together across the joins the unit tests take apart: a
database created by one version of the schema, migrated forward, written to,
closed, reopened, and still agreeing with itself.
"""

from datetime import date
from decimal import Decimal

import pytest

from hatchlot.errors import NotFoundError
from hatchlot.identifiers import LotCode
from hatchlot.quantities.base import Quantity
from hatchlot.rearing.container import Container, ContainerKind, ContainerRegister
from hatchlot.rearing.inventory import take_inventory
from hatchlot.rearing.ledger import EntryKind, LedgerEntry
from hatchlot.rearing.lot import RearingLot
from hatchlot.station import StationProfile
from hatchlot.store.db import StoreError, connect, table_names
from hatchlot.store.lots import load_lot, save_entry, save_lot
from hatchlot.store.migrations import current_version, migrate
from hatchlot.store.schema import ALL, latest_version
from hatchlot.store.session import open_session, session
from hatchlot.units import System
from hatchlot.water.source import SourceKind, SourceRegister, WaterSource


def sources():
    register = SourceRegister()
    register.add(
        WaterSource(
            code="SP-1",
            name="upper spring",
            kind=SourceKind.SPRING,
            design_flow=Quantity(900, "gpm"),
            minimum_flow=Quantity(600, "gpm"),
        )
    )
    return register


def containers(*codes):
    register = ContainerRegister()
    for code in codes or ("RW-1",):
        register.add(
            Container(
                code=code,
                kind=ContainerKind.RACEWAY,
                length=Quantity(30, "m"),
                width=Quantity(3, "m"),
                depth=Quantity(1, "m"),
                flow=Quantity(450, "gpm"),
                water_source="SP-1",
            )
        )
    return register


def lot(sequence=1, container="RW-1", population="40000"):
    return RearingLot(
        code=LotCode(2024, "CHK", sequence),
        container=container,
        ponded_on=date(2025, 1, 15),
        population=Decimal(population),
        mean_weight=Quantity("2.5", "g"),
    )


def test_a_database_survives_being_closed_and_reopened(tmp_path):
    path = str(tmp_path / "station.sqlite3")
    with session(path) as first:
        first.save_profile(StationProfile(code="CC", name="Cold Creek", system=System.METRIC))
        first.save_station(sources(), containers("RW-1", "RW-2"))
        first.save_lots([lot(1), lot(2, container="RW-2")])
        save_entry(
            first.connection,
            LedgerEntry("2025-01-15", "2024-CHK-01", EntryKind.PONDED, 40000, "kt"),
        )
    with session(path) as second:
        assert second.is_current
        assert second.profile().name == "Cold Creek"
        assert len(second.containers()) == 2
        assert len(second.lots()) == 2
        assert second.ledger(lot="2024-CHK-01").balance("2024-CHK-01").closing == Decimal(40000)


def test_a_database_migrates_forward_from_a_partly_built_schema(tmp_path):
    path = str(tmp_path / "old.sqlite3")
    connection = connect_to(path)
    migrate(connection, ALL[:2])
    assert current_version(connection) == 2
    assert "ledger_entry" not in table_names(connection)
    connection.close()
    with session(path) as brought_forward:
        assert brought_forward.version == latest_version()
        assert "ledger_entry" in table_names(brought_forward.connection)


def connect_to(path):
    from hatchlot.store.db import Settings

    return connect(Settings(path=path))


def test_nothing_is_lost_when_a_migration_runs_over_existing_rows(tmp_path):
    path = str(tmp_path / "growing.sqlite3")
    connection = connect_to(path)
    migrate(connection, ALL[:2])
    connection.execute(
        "INSERT INTO container (code, kind, length_m, width_m, depth_m, flow_gpm) "
        "VALUES ('RW-1', 'raceway', '30', '3', '1', '450')"
    )
    connection.close()
    with session(path) as brought_forward:
        assert len(brought_forward.containers()) == 1
        brought_forward.save_lots([lot(1)])
        assert len(brought_forward.lots()) == 1


def test_the_lot_and_its_ledger_still_reconcile_after_a_reopen(tmp_path):
    path = str(tmp_path / "station.sqlite3")
    with session(path) as first:
        first.save_station(sources(), containers())
        first.save_lots([lot(1, population="40000")])
        save_entry(
            first.connection,
            LedgerEntry("2025-01-15", "2024-CHK-01", EntryKind.PONDED, 40000, "kt"),
        )
        record = load_lot(first.connection, "2024-CHK-01")
        record.remove(Decimal(500))
        save_lot(first.connection, record)
        save_entry(
            first.connection,
            LedgerEntry("2025-02-01", "2024-CHK-01", EntryKind.MORTALITY, 500, "kt", "fungus"),
        )
    with session(path) as second:
        lots = list(second.lots())
        inventory = take_inventory(lots, second.containers(), second.ledger(), "2025-03-01")
        assert inventory.is_clean
        assert inventory.population == Decimal(39500)


def test_a_lot_pointing_at_a_container_that_was_never_saved_is_refused(tmp_path):
    path = str(tmp_path / "station.sqlite3")
    with session(path) as opened:
        opened.save_station(sources(), containers())
        with pytest.raises(StoreError):
            opened.save_lots([lot(1, container="RW-9")])
        assert len(opened.lots()) == 0


def test_a_missing_lot_is_a_not_found_however_it_is_asked_for(tmp_path):
    path = str(tmp_path / "station.sqlite3")
    with session(path) as opened, pytest.raises(NotFoundError):
        load_lot(opened.connection, "2024-CHK-09")


def test_two_sessions_on_one_file_see_each_other_s_writes(tmp_path):
    path = str(tmp_path / "station.sqlite3")
    writer = open_session(path)
    reader = open_session(path)
    writer.save_station(sources(), containers())
    writer.save_lots([lot(1)])
    assert len(reader.lots()) == 1
    writer.close()
    reader.close()
