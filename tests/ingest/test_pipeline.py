from decimal import Decimal

import pytest

from hatchlot.errors import ValidationError
from hatchlot.ingest import ImportLedger, Profile, run_import
from hatchlot.ingest.pipeline import import_rate, rows_of, run_with_profiles
from hatchlot.ingest.profile import ColumnMap, FieldKind

KEYS = ("taken_at",)


def profile(code="DL-1"):
    entry = Profile(code=code, description="datalogger")
    entry.add(ColumnMap(column="DateTime", name="taken_at", kind=FieldKind.TIMESTAMP))
    entry.add(
        ColumnMap(
            column="Temp_F",
            name="temperature",
            kind=FieldKind.QUANTITY,
            source_unit="F",
            target_unit="C",
        )
    )
    return entry


GOOD = "DateTime,Temp_F\n2025-03-01 06:00,50\n2025-03-02 06:00,51\n"
OVERLAP = "DateTime,Temp_F\n2025-03-02 06:00,51\n2025-03-03 06:00,52\n"


def test_a_first_import_takes_everything():
    report = run_import(profile(), GOOD, ImportLedger(), KEYS)
    assert report.imported == 2
    assert report.duplicates == 0
    assert report.rejected == 0
    assert report.is_clean
    assert "2 rows in" in report.line()


def test_the_same_file_again_does_nothing_at_all():
    ledger = ImportLedger()
    run_import(profile(), GOOD, ledger, KEYS)
    second = run_import(profile(), GOOD, ledger, KEYS)
    assert second.skipped_as_seen_file
    assert second.imported == 0
    assert not second.is_clean
    assert "already imported" in second.line()


def test_an_overlapping_export_takes_only_the_new_rows():
    ledger = ImportLedger()
    run_import(profile(), GOOD, ledger, KEYS)
    second = run_import(profile(), OVERLAP, ledger, KEYS)
    assert second.imported == 1
    assert second.duplicates == 1


def test_a_file_with_a_few_bad_rows_still_imports_the_rest():
    text = "DateTime,Temp_F\n" + "".join(
        f"2025-03-{day:02d} 06:00,{'bad' if day == 3 else 50}\n" for day in range(1, 11)
    )
    report = run_import(profile(), text, ImportLedger(), KEYS)
    assert report.imported == 9
    assert report.rejected == 1
    assert not report.is_clean


def test_a_file_that_is_mostly_unreadable_is_refused_outright():
    text = "DateTime,Temp_F\n" + "".join(f"2025-03-{day:02d} 06:00,bad\n" for day in range(1, 6))
    ledger = ImportLedger()
    with pytest.raises(ValidationError):
        run_import(profile(), text, ledger, KEYS)
    assert len(ledger) == 0
    assert ledger.file_count == 0


def test_the_rejection_ceiling_can_be_moved():
    text = "DateTime,Temp_F\n2025-03-01 06:00,50\n2025-03-02 06:00,bad\n"
    report = run_import(profile(), text, ImportLedger(), KEYS, reject_ceiling="0.6")
    assert report.imported == 1


def test_an_impossible_ceiling_is_refused():
    with pytest.raises(ValidationError):
        run_import(profile(), GOOD, ImportLedger(), KEYS, reject_ceiling="1.5")


def test_the_rows_an_import_took_in():
    report = run_import(profile(), GOOD, ImportLedger(), KEYS)
    rows = rows_of(report)
    assert len(rows) == 2
    assert rows[0]["temperature"].symbol == "C"


def test_a_skipped_file_has_no_rows():
    ledger = ImportLedger()
    run_import(profile(), GOOD, ledger, KEYS)
    assert rows_of(run_import(profile(), GOOD, ledger, KEYS)) == ()


def test_the_share_of_a_file_that_ended_up_imported():
    report = run_import(profile(), GOOD, ImportLedger(), KEYS)
    assert import_rate(report) == Decimal(1)
    ledger = ImportLedger()
    run_import(profile(), GOOD, ledger, KEYS)
    assert import_rate(run_import(profile(), OVERLAP, ledger, KEYS)) == Decimal("0.5")


def test_an_empty_import_has_no_rate():
    ledger = ImportLedger()
    run_import(profile(), GOOD, ledger, KEYS)
    assert import_rate(run_import(profile(), GOOD, ledger, KEYS)) == Decimal(0)


def test_the_profile_can_be_chosen_off_the_file_header():
    scale = Profile(code="SC-1", description="scale")
    scale.add(ColumnMap(column="date", name="day", kind=FieldKind.DATE))
    report = run_with_profiles([profile(), scale], GOOD, ImportLedger(), KEYS)
    assert report.profile == "DL-1"


def test_a_file_no_profile_fits_is_refused():
    with pytest.raises(ValidationError):
        run_with_profiles([profile()], "a,b\n1,2\n", ImportLedger(), KEYS)


def test_an_empty_file_is_refused_before_a_profile_is_chosen():
    with pytest.raises(ValidationError):
        run_with_profiles([profile()], "", ImportLedger(), KEYS)
