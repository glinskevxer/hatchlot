import sqlite3

import pytest

from hatchlot.errors import ValidationError
from hatchlot.store.db import StoreError, connect, execute, query, table_names
from hatchlot.store.migrations import (
    LEDGER_TABLE,
    Migration,
    applied,
    applied_at,
    current_version,
    history,
    is_up_to_date,
    migrate,
    pending,
)


def first():
    return Migration(
        version=1,
        name="containers",
        statements=("CREATE TABLE container (code TEXT PRIMARY KEY)",),
    )


def second():
    return Migration(
        version=2,
        name="lots",
        statements=(
            "CREATE TABLE lot (code TEXT PRIMARY KEY, container TEXT NOT NULL)",
            "CREATE INDEX lot_container ON lot (container)",
        ),
    )


def test_a_migration_needs_a_version_a_name_and_something_to_do():
    with pytest.raises(ValidationError):
        Migration(version=0, name="x", statements=("SELECT 1",))
    with pytest.raises(ValidationError):
        Migration(version=1, name="  ", statements=("SELECT 1",))
    with pytest.raises(ValidationError):
        Migration(version=1, name="x", statements=())
    with pytest.raises(ValidationError):
        Migration(version=1, name="x", statements=("  ",))


def test_the_checksum_is_over_the_statements():
    assert first().checksum == first().checksum
    changed = Migration(
        version=1, name="containers", statements=("CREATE TABLE container (code TEXT)",)
    )
    assert changed.checksum != first().checksum


def test_a_fresh_database_is_at_version_zero():
    connection = connect()
    assert current_version(connection) == 0
    assert applied(connection) == {}
    assert LEDGER_TABLE in table_names(connection)


def test_migrating_runs_everything_and_records_it():
    connection = connect()
    assert migrate(connection, [first(), second()]) == (1, 2)
    assert current_version(connection) == 2
    assert "container" in table_names(connection)
    assert "lot" in table_names(connection)


def test_migrating_twice_runs_nothing_the_second_time():
    connection = connect()
    migrate(connection, [first(), second()])
    assert migrate(connection, [first(), second()]) == ()
    assert is_up_to_date(connection, [first(), second()])


def test_a_new_migration_runs_on_a_database_that_is_behind():
    connection = connect()
    migrate(connection, [first()])
    assert not is_up_to_date(connection, [first(), second()])
    assert migrate(connection, [first(), second()]) == (2,)


def test_an_edited_migration_is_refused_rather_than_rerun():
    connection = connect()
    migrate(connection, [first()])
    edited = Migration(
        version=1,
        name="containers",
        statements=("CREATE TABLE container (code TEXT PRIMARY KEY, name TEXT)",),
    )
    with pytest.raises(StoreError) as excinfo:
        pending(connection, [edited])
    assert "has changed" in str(excinfo.value)


def test_two_migrations_on_one_version_are_refused():
    connection = connect()
    with pytest.raises(ValidationError):
        pending(connection, [first(), first()])


def test_migrations_out_of_order_are_refused():
    connection = connect()
    with pytest.raises(ValidationError):
        pending(connection, [second(), first()])


def test_a_failing_migration_leaves_nothing_behind():
    connection = connect()
    broken = Migration(version=1, name="broken", statements=("CREATE TABLE (",))
    with pytest.raises(sqlite3.OperationalError):
        migrate(connection, [broken])
    assert current_version(connection) == 0
    assert "container" not in table_names(connection)


def test_a_migration_that_fails_halfway_rolls_back_the_first_half():
    connection = connect()
    half = Migration(
        version=1,
        name="half",
        statements=("CREATE TABLE good (code TEXT)", "CREATE TABLE ("),
    )
    with pytest.raises(sqlite3.OperationalError):
        migrate(connection, [half])
    assert "good" not in table_names(connection)


def test_the_history_says_what_ran_and_when():
    connection = connect()
    migrate(connection, [first(), second()])
    entries = history(connection)
    assert [entry[0] for entry in entries] == [1, 2]
    assert entries[0][1] == "containers"
    assert applied_at(connection, 1) is not None
    assert applied_at(connection, 9) is None


def test_the_ledger_is_written_in_the_same_transaction_as_the_change():
    connection = connect()
    migrate(connection, [first()])
    rows = query(connection, f"SELECT * FROM {LEDGER_TABLE}")
    assert len(rows) == 1
    execute(connection, "INSERT INTO container (code) VALUES ('RW-1')")
    assert len(query(connection, "SELECT * FROM container")) == 1
