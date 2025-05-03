import sqlite3
from decimal import Decimal

import pytest

from hatchlot.errors import ValidationError
from hatchlot.store.db import (
    Settings,
    StoreError,
    column_names,
    connect,
    execute,
    foreign_keys_on,
    query,
    query_one,
    table_names,
    transaction,
)


def memory():
    connection = connect()
    execute(
        connection,
        "CREATE TABLE lot (code TEXT PRIMARY KEY, fish DECIMAL NOT NULL)",
    )
    return connection


def test_a_memory_connection_comes_up_with_foreign_keys_on():
    connection = connect()
    assert foreign_keys_on(connection)


def test_the_settings_refuse_an_impossible_timeout_or_journal_mode():
    with pytest.raises(ValidationError):
        Settings(timeout_seconds=0)
    with pytest.raises(ValidationError):
        Settings(journal_mode="sideways")


def test_a_file_connection_opens_and_reopens(tmp_path):
    path = str(tmp_path / "station.sqlite3")
    first = connect(Settings(path=path))
    execute(first, "CREATE TABLE lot (code TEXT PRIMARY KEY)")
    execute(first, "INSERT INTO lot (code) VALUES ('2024-CHK-01')")
    first.close()
    second = connect(Settings(path=path))
    assert table_names(second) == ("lot",)


def test_a_path_in_a_directory_that_does_not_exist_is_refused(tmp_path):
    with pytest.raises(ValidationError):
        connect(Settings(path=str(tmp_path / "nowhere" / "station.sqlite3")))


def test_a_decimal_survives_a_round_trip():
    connection = memory()
    execute(
        connection, "INSERT INTO lot (code, fish) VALUES (?, ?)", "2024-CHK-01", Decimal("9500.25")
    )
    row = query_one(connection, "SELECT fish FROM lot WHERE code = ?", "2024-CHK-01")
    assert row is not None
    assert row["fish"] == Decimal("9500.25")


def test_a_stored_value_that_is_not_a_number_is_refused_on_the_way_out():
    connection = memory()
    execute(connection, "INSERT INTO lot (code, fish) VALUES ('x', 'not a number')")
    with pytest.raises(ValidationError):
        query(connection, "SELECT fish FROM lot")


def test_a_transaction_commits_what_it_did():
    connection = memory()
    with transaction(connection):
        execute(connection, "INSERT INTO lot (code, fish) VALUES ('a', '1')")
    assert len(query(connection, "SELECT * FROM lot")) == 1


def test_a_transaction_rolls_back_on_anything_raised():
    connection = memory()
    with pytest.raises(RuntimeError), transaction(connection):
        execute(connection, "INSERT INTO lot (code, fish) VALUES ('a', '1')")
        raise RuntimeError("something went wrong")
    assert query(connection, "SELECT * FROM lot") == []


def test_a_nested_transaction_is_refused_rather_than_flattened():
    connection = memory()
    with transaction(connection), pytest.raises(StoreError), transaction(connection):
        pass


def test_a_broken_constraint_comes_back_as_a_store_error():
    connection = memory()
    execute(connection, "INSERT INTO lot (code, fish) VALUES ('a', '1')")
    with pytest.raises(StoreError):
        execute(connection, "INSERT INTO lot (code, fish) VALUES ('a', '2')")


def test_query_one_refuses_more_than_one_row():
    connection = memory()
    execute(connection, "INSERT INTO lot (code, fish) VALUES ('a', '1')")
    execute(connection, "INSERT INTO lot (code, fish) VALUES ('b', '2')")
    assert query_one(connection, "SELECT * FROM lot WHERE code = 'a'") is not None
    assert query_one(connection, "SELECT * FROM lot WHERE code = 'z'") is None
    with pytest.raises(StoreError):
        query_one(connection, "SELECT * FROM lot")


def test_execute_says_how_many_rows_it_touched():
    connection = memory()
    execute(connection, "INSERT INTO lot (code, fish) VALUES ('a', '1')")
    assert execute(connection, "UPDATE lot SET fish = '2' WHERE code = 'a'") == 1
    assert execute(connection, "DELETE FROM lot WHERE code = 'z'") == 0


def test_the_tables_and_columns_can_be_listed():
    connection = memory()
    assert table_names(connection) == ("lot",)
    assert column_names(connection, "lot") == ("code", "fish")
    with pytest.raises(ValidationError):
        column_names(connection, "nothing")


def test_rows_come_back_addressable_by_name():
    connection = memory()
    execute(connection, "INSERT INTO lot (code, fish) VALUES ('a', '1')")
    row = query(connection, "SELECT * FROM lot")[0]
    assert isinstance(row, sqlite3.Row)
    assert row["code"] == "a"
