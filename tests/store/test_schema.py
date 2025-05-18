import pytest

from hatchlot.errors import ValidationError
from hatchlot.store.db import (
    StoreError,
    column_names,
    connect,
    execute,
    foreign_keys_on,
    table_names,
)
from hatchlot.store.migrations import current_version, is_up_to_date, migrate
from hatchlot.store.schema import ALL, latest_version, migration_named


def migrated():
    connection = connect()
    migrate(connection, ALL)
    return connection


def test_the_schema_migrates_from_nothing():
    connection = migrated()
    assert current_version(connection) == latest_version()
    assert is_up_to_date(connection, ALL)


def test_every_table_the_station_needs_is_there():
    tables = set(table_names(migrated()))
    for name in (
        "water_source",
        "container",
        "rearing_lot",
        "ledger_entry",
        "water_reading",
        "feeding",
        "mortality",
        "station",
    ):
        assert name in tables


def test_the_container_table_has_the_columns_the_engine_expects():
    columns = column_names(migrated(), "container")
    assert "flow_gpm" in columns
    assert "water_source" in columns
    assert "out_of_service" in columns


def test_a_lot_cannot_point_at_a_container_that_is_not_there():
    connection = migrated()
    assert foreign_keys_on(connection)
    with pytest.raises(StoreError):
        execute(
            connection,
            "INSERT INTO rearing_lot (code, container, species, ponded_on, population, "
            "mean_weight_g, state) VALUES ('2024-CHK-01', 'RW-9', 'CHK', '2025-01-15', "
            "'1000', '2.5', 'rearing')",
        )


def test_a_lot_in_a_container_that_is_there_goes_in():
    connection = migrated()
    execute(
        connection,
        "INSERT INTO container (code, kind, length_m, width_m, depth_m, flow_gpm) "
        "VALUES ('RW-1', 'raceway', '30', '3', '1', '500')",
    )
    execute(
        connection,
        "INSERT INTO rearing_lot (code, container, species, ponded_on, population, "
        "mean_weight_g, state) VALUES ('2024-CHK-01', 'RW-1', 'CHK', '2025-01-15', "
        "'1000', '2.5', 'rearing')",
    )
    assert current_version(connection) == latest_version()


def test_a_reading_is_unique_per_unit_and_time():
    connection = migrated()
    execute(
        connection,
        "INSERT INTO water_reading (taken_at, container, celsius, oxygen_mgl) "
        "VALUES ('2025-03-01T06:00:00', 'RW-1', '10', '9')",
    )
    with pytest.raises(StoreError):
        execute(
            connection,
            "INSERT INTO water_reading (taken_at, container, celsius, oxygen_mgl) "
            "VALUES ('2025-03-01T06:00:00', 'RW-1', '11', '9')",
        )


def test_the_migrations_are_numbered_in_order_with_no_gaps():
    versions = [migration.version for migration in ALL]
    assert versions == list(range(1, len(ALL) + 1))


def test_every_migration_has_a_distinct_checksum():
    checksums = {migration.checksum for migration in ALL}
    assert len(checksums) == len(ALL)


def test_a_migration_can_be_found_by_name():
    assert migration_named("rearing lots").version == 2
    with pytest.raises(ValidationError):
        migration_named("nothing like that")
