from decimal import Decimal

import pytest

from hatchlot.errors import ValidationError
from hatchlot.quantities.base import Quantity
from hatchlot.quantities.temperature import Temperature
from hatchlot.reporting.export import to_csv, to_records, write_csv


def test_a_plain_table_exports_as_it_stands():
    text = to_csv(["lot", "fish"], [["2024-CHK-01", Decimal(50000)]])
    assert text == "lot,fish\n2024-CHK-01,50000\n"


def test_a_quantity_goes_out_as_two_columns_so_it_adds_up():
    text = to_csv(["weight"], [[Quantity("2.5", "g")]])
    lines = text.splitlines()
    assert lines[0] == "weight,weight_unit"
    assert lines[1] == "2.5,g"


def test_a_temperature_goes_out_with_its_scale():
    text = to_csv(["water"], [[Temperature(50, "F")]])
    assert text.splitlines()[0] == "water,water_scale"
    assert text.splitlines()[1] == "50,F"


def test_numbers_go_out_unrounded():
    text = to_csv(["value"], [[Decimal("1.23456789")]])
    assert "1.23456789" in text


def test_none_and_booleans_have_a_written_form():
    text = to_csv(["a", "b", "c"], [[None, True, False]])
    assert text.splitlines()[1] == ",true,false"


def test_an_export_with_no_headings_or_a_repeat_is_refused():
    with pytest.raises(ValidationError):
        to_csv([], [])
    with pytest.raises(ValidationError):
        to_csv(["a", "a"], [])


def test_a_ragged_row_is_refused():
    with pytest.raises(ValidationError):
        to_csv(["a", "b"], [["one"]])


def test_rows_that_expand_differently_are_refused():
    with pytest.raises(ValidationError):
        to_csv(["value"], [[Quantity(1, "g")], [Decimal(1)]])


def test_an_export_with_no_rows_still_has_its_headings():
    assert to_csv(["lot", "fish"], []) == "lot,fish\n"


def test_a_field_with_a_comma_in_it_is_quoted():
    text = to_csv(["note"], [["one, two"]])
    assert '"one, two"' in text


def test_the_same_rows_come_back_as_records():
    records = to_records(["lot", "weight"], [["2024-CHK-01", Quantity("2.5", "g")]])
    assert records[0]["lot"] == "2024-CHK-01"
    assert records[0]["weight"] == "2.5"
    assert records[0]["weight_unit"] == "g"


def test_an_export_writes_to_a_file(tmp_path):
    path = tmp_path / "lots.csv"
    assert write_csv(str(path), ["lot"], [["2024-CHK-01"], ["2024-CHK-02"]]) == 2
    assert path.read_text(encoding="utf-8").splitlines()[0] == "lot"


def test_a_path_that_cannot_be_written_is_refused(tmp_path):
    with pytest.raises(ValidationError):
        write_csv(str(tmp_path), ["lot"], [["2024-CHK-01"]])
    with pytest.raises(ValidationError):
        write_csv(str(tmp_path / "nowhere" / "lots.csv"), ["lot"], [["2024-CHK-01"]])
