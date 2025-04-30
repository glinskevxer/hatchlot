from datetime import datetime
from decimal import Decimal

import pytest

from hatchlot.errors import ValidationError
from hatchlot.ingest.dedupe import (
    ImportLedger,
    commit_rows,
    dedupe,
    file_hash,
    overlap_share,
    row_key,
)
from hatchlot.quantities.base import Quantity

KEYS = ("taken_at", "container")


def row(stamp="2025-03-01 06:00", container="RW-1", value="10"):
    return {
        "taken_at": datetime.fromisoformat(stamp),
        "container": container,
        "temperature": Quantity(value, "C"),
    }


def test_the_same_text_hashes_the_same_and_different_text_does_not():
    assert file_hash("abc") == file_hash("abc")
    assert file_hash("abc") != file_hash("abd")


def test_a_row_key_is_over_the_fields_that_identify_it():
    assert row_key(row(), KEYS) == row_key(row(value="12"), KEYS)
    assert row_key(row(), KEYS) != row_key(row(container="RW-2"), KEYS)


def test_a_row_key_ignores_the_shape_a_value_arrived_in():
    first = {"taken_at": datetime(2025, 3, 1, 6, 0), "container": "RW-1"}
    second = {"taken_at": datetime(2025, 3, 1, 6, 0), "container": " rw-1 "}
    assert row_key(first, KEYS) == row_key(second, KEYS)


def test_a_quantity_and_a_decimal_both_canonicalise():
    first = {"a": Quantity("10.50", "C"), "b": Decimal("1.500")}
    second = {"a": Quantity("10.5", "C"), "b": Decimal("1.5")}
    assert row_key(first, ("a", "b")) == row_key(second, ("a", "b"))


def test_a_row_key_needs_fields_and_the_row_to_have_them():
    with pytest.raises(ValidationError):
        row_key(row(), ())
    with pytest.raises(ValidationError):
        row_key(row(), ("missing",))


def test_a_ledger_remembers_a_file_it_has_seen():
    ledger = ImportLedger()
    assert not ledger.seen_file("text")
    ledger.record_file("text")
    assert ledger.seen_file("text")
    assert ledger.file_count == 1


def test_a_ledger_remembers_a_row_it_has_seen():
    ledger = ImportLedger()
    assert not ledger.seen_row(row(), KEYS)
    ledger.record_row(row(), KEYS)
    assert ledger.seen_row(row(), KEYS)
    assert len(ledger) == 1


def test_a_first_import_keeps_everything():
    result = dedupe([row(), row(stamp="2025-03-01 07:00")], KEYS, ImportLedger())
    assert result.kept == 2
    assert result.is_all_new
    assert overlap_share(result) == Decimal(0)


def test_a_second_import_of_the_same_rows_keeps_none():
    ledger = ImportLedger()
    rows = [row(), row(stamp="2025-03-01 07:00")]
    first = dedupe(rows, KEYS, ledger)
    commit_rows(first, KEYS, ledger)
    second = dedupe(rows, KEYS, ledger)
    assert second.kept == 0
    assert len(second.duplicates) == 2
    assert overlap_share(second) == Decimal(1)


def test_an_overlapping_export_keeps_only_the_new_rows():
    ledger = ImportLedger()
    first = dedupe([row(stamp="2025-03-01 06:00")], KEYS, ledger)
    commit_rows(first, KEYS, ledger)
    second = dedupe([row(stamp="2025-03-01 06:00"), row(stamp="2025-03-01 07:00")], KEYS, ledger)
    assert second.kept == 1
    assert len(second.duplicates) == 1
    assert overlap_share(second) == Decimal("0.5")


def test_a_row_repeated_inside_one_file_is_counted_separately():
    result = dedupe([row(), row()], KEYS, ImportLedger())
    assert result.kept == 1
    assert result.within_file == 1
    assert result.duplicates == ()
    assert not result.is_all_new


def test_committing_puts_the_fresh_rows_in_the_ledger():
    ledger = ImportLedger()
    result = dedupe([row(), row(stamp="2025-03-01 07:00")], KEYS, ledger)
    assert commit_rows(result, KEYS, ledger) == 2
    assert len(ledger) == 2


def test_an_empty_import_has_no_overlap_to_report():
    result = dedupe([], KEYS, ImportLedger())
    assert overlap_share(result) == Decimal(0)
    assert result.kept == 0
