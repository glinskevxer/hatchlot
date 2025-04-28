from datetime import date, datetime
from decimal import Decimal

import pytest

from hatchlot.errors import ValidationError
from hatchlot.ingest.profile import ColumnMap, FieldKind, Profile
from hatchlot.ingest.reader import read_file, read_rows, rejected_summary
from hatchlot.numeric import quantize
from hatchlot.quantities.base import Quantity


def profile(skip=0, delimiter=","):
    entry = Profile(code="DL-1", description="datalogger", delimiter=delimiter, skip_rows=skip)
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
    entry.add(ColumnMap(column="Note", name="note", kind=FieldKind.TEXT, required=False))
    return entry


GOOD = "DateTime,Temp_F,Note\n2025-03-01 06:00,50,ok\n2025-03-02 06:00,51.8,\n"


def test_a_clean_file_reads_every_row():
    result = read_rows(profile(), GOOD)
    assert result.read == 2
    assert result.is_clean
    assert result.acceptance == Decimal(1)
    assert result.rows[0]["taken_at"] == datetime(2025, 3, 1, 6, 0)
    assert quantize(result.rows[0]["temperature"].to("C").amount, 2) == Decimal("10.00")


def test_an_optional_column_left_blank_is_simply_absent():
    result = read_rows(profile(), GOOD)
    assert result.rows[0]["note"] == "ok"
    assert "note" not in result.rows[1]


def test_a_bad_row_is_quarantined_and_the_rest_still_read():
    text = "DateTime,Temp_F\n2025-03-01 06:00,50\n2025-03-02 06:00,not a number\n"
    result = read_rows(profile(), text)
    assert result.read == 1
    assert len(result.rejected) == 1
    assert result.rejected[0].line == 3
    assert "temperature" in result.rejected[0].reason
    assert result.acceptance == Decimal("0.5")


def test_a_missing_required_value_is_a_rejection_not_a_crash():
    text = "DateTime,Temp_F\n2025-03-01 06:00,\n"
    result = read_rows(profile(), text)
    assert result.read == 0
    assert "Temp_F is empty" in result.rejected[0].reason


def test_a_rejected_row_keeps_what_it_had():
    text = "DateTime,Temp_F\n2025-03-01 06:00,rubbish\n"
    result = read_rows(profile(), text)
    assert result.rejected[0].raw["Temp_F"] == "rubbish"
    assert "line 2" in result.rejected[0].summary


def test_a_file_missing_a_required_column_is_refused_outright():
    with pytest.raises(ValidationError):
        read_rows(profile(), "DateTime\n2025-03-01 06:00\n")


def test_an_empty_file_is_refused():
    with pytest.raises(ValidationError):
        read_rows(profile(), "")


def test_a_file_with_a_preamble_can_be_skipped_past():
    text = "exported by vendor\n\nDateTime,Temp_F\n2025-03-01 06:00,50\n"
    result = read_rows(profile(skip=2), text)
    assert result.read == 1
    assert result.rows[0]["temperature"].symbol == "C"


def test_a_semicolon_file_reads_on_its_own_delimiter():
    text = "DateTime;Temp_F\n2025-03-01 06:00;50\n"
    result = read_rows(profile(delimiter=";"), text)
    assert result.read == 1


def test_a_column_of_values_can_be_pulled_out():
    result = read_rows(profile(), GOOD)
    assert len(result.column("temperature")) == 2
    assert result.column("missing") == ()


def test_a_date_column_reads_as_a_date():
    entry = Profile(code="SC-1", description="scale")
    entry.add(ColumnMap(column="date", name="day", kind=FieldKind.DATE))
    entry.add(ColumnMap(column="count", name="fish", kind=FieldKind.NUMBER))
    result = read_rows(entry, "date,count\n2025-03-01,1250\n")
    assert result.rows[0]["day"] == date(2025, 3, 1)
    assert result.rows[0]["fish"] == Decimal(1250)


def test_a_number_column_that_is_not_a_number_is_quarantined():
    entry = Profile(code="SC-1", description="scale")
    entry.add(ColumnMap(column="count", name="fish", kind=FieldKind.NUMBER))
    result = read_rows(entry, "count\nx\n")
    assert result.read == 0
    assert len(result.rejected) == 1


def test_a_quantity_column_comes_back_as_a_quantity():
    result = read_rows(profile(), GOOD)
    assert isinstance(result.rows[0]["temperature"], Quantity)


def test_the_first_few_rejections_are_summarised():
    text = "DateTime,Temp_F\n" + "".join(f"2025-03-{day:02d} 06:00,bad\n" for day in range(1, 10))
    result = read_rows(profile(), text)
    assert len(rejected_summary(result)) == 5
    assert len(rejected_summary(result, limit=2)) == 2
    with pytest.raises(ValidationError):
        rejected_summary(result, limit=0)


def test_a_file_off_disk_reads_the_same_way(tmp_path):
    path = tmp_path / "export.csv"
    path.write_text(GOOD, encoding="utf-8")
    result = read_file(profile(), str(path))
    assert result.read == 2


def test_a_file_that_is_not_there_or_is_not_text_is_refused(tmp_path):
    with pytest.raises(ValidationError):
        read_file(profile(), str(tmp_path / "nothing.csv"))
    binary = tmp_path / "binary.csv"
    binary.write_bytes(b"\xff\xfe\x00\x01")
    with pytest.raises(ValidationError):
        read_file(profile(), str(binary))


def test_an_import_with_nothing_in_it_has_no_acceptance_to_report():
    result = read_rows(profile(), "DateTime,Temp_F\n")
    assert result.read == 0
    assert result.acceptance == Decimal(0)
