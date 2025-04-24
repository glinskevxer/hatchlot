from decimal import Decimal

import pytest

from hatchlot.errors import ValidationError
from hatchlot.ingest.profile import (
    ColumnMap,
    FieldKind,
    Profile,
    choose_profile,
    describe_row,
)
from hatchlot.numeric import quantize
from hatchlot.units import Dimension


def column(
    source="Temp_F",
    name="temperature",
    kind=FieldKind.QUANTITY,
    source_unit="F",
    target_unit="C",
    required=True,
):
    return ColumnMap(
        column=source,
        name=name,
        kind=kind,
        source_unit=source_unit,
        target_unit=target_unit,
        required=required,
    )


def profile(code="DL-1", columns=None):
    entry = Profile(code=code, description="datalogger export")
    for item in columns or [
        ColumnMap(column="DateTime", name="taken_at", kind=FieldKind.TIMESTAMP),
        column(),
    ]:
        entry.add(item)
    return entry


def test_a_quantity_column_converts_into_the_station_unit():
    assert quantize(column().convert(50), 4) == Decimal("10.0000")
    assert column().dimension is Dimension.TEMPERATURE


def test_a_plain_column_passes_its_number_through():
    plain = ColumnMap(column="count", name="fish", kind=FieldKind.NUMBER)
    assert plain.convert("1250") == Decimal(1250)
    assert plain.dimension is None


def test_a_quantity_column_needs_both_units_and_one_dimension():
    with pytest.raises(ValidationError):
        column(source_unit="", target_unit="C")
    with pytest.raises(ValidationError):
        column(source_unit="F", target_unit="kg")


def test_a_column_that_is_not_a_quantity_takes_no_units():
    with pytest.raises(ValidationError):
        ColumnMap(column="count", name="fish", kind=FieldKind.NUMBER, source_unit="kg")


def test_a_column_needs_a_column_a_name_and_a_real_kind():
    with pytest.raises(ValidationError):
        ColumnMap(column=" ", name="fish", kind=FieldKind.NUMBER)
    with pytest.raises(ValidationError):
        ColumnMap(column="count", name="  ", kind=FieldKind.NUMBER)
    with pytest.raises(ValidationError):
        ColumnMap(column="count", name="fish", kind="number")  # type: ignore[arg-type]


def test_only_a_quantity_column_needs_a_unit():
    assert FieldKind.QUANTITY.needs_unit
    assert not FieldKind.DATE.needs_unit


def test_a_profile_normalises_its_code_and_needs_a_description():
    assert profile(code=" dl 1 ").code == "DL-1"
    with pytest.raises(ValidationError):
        Profile(code="DL-1", description="   ")


def test_a_profile_refuses_a_repeated_name_or_column():
    entry = profile()
    with pytest.raises(ValidationError):
        entry.add(column(source="Other", name="temperature"))
    with pytest.raises(ValidationError):
        entry.add(column(source="Temp_F", name="other"))


def test_a_profile_built_with_duplicate_names_is_refused():
    with pytest.raises(ValidationError):
        Profile(
            code="DL-1",
            description="x",
            columns=[
                ColumnMap(column="a", name="temperature", kind=FieldKind.NUMBER),
                ColumnMap(column="b", name="temperature", kind=FieldKind.NUMBER),
            ],
        )


def test_an_impossible_delimiter_or_skip_is_refused():
    with pytest.raises(ValidationError):
        Profile(code="DL-1", description="x", delimiter="||")
    with pytest.raises(ValidationError):
        Profile(code="DL-1", description="x", skip_rows=-1)


def test_a_profile_says_which_required_columns_a_file_is_missing():
    entry = profile()
    assert entry.matches(["DateTime", "Temp_F"])
    assert entry.missing_from(["DateTime"]) == ("Temp_F",)
    assert not entry.matches(["DateTime"])


def test_an_optional_column_is_not_required_to_match():
    entry = profile()
    entry.add(
        column(
            source="Note",
            name="note",
            kind=FieldKind.TEXT,
            source_unit="",
            target_unit="",
            required=False,
        )
    )
    assert entry.matches(["DateTime", "Temp_F"])
    assert entry.names() == ("taken_at", "temperature", "note")


def test_looking_a_column_up_by_name():
    entry = profile()
    assert entry.by_name("temperature").column == "Temp_F"
    with pytest.raises(ValidationError):
        entry.by_name("weight")


def test_the_profile_that_fits_a_file_is_chosen():
    datalogger = profile(code="DL-1")
    scale = Profile(code="SC-1", description="scale export")
    scale.add(ColumnMap(column="date", name="day", kind=FieldKind.DATE))
    scale.add(
        ColumnMap(
            column="net_wt_lb",
            name="weight",
            kind=FieldKind.QUANTITY,
            source_unit="lb",
            target_unit="kg",
        )
    )
    assert choose_profile([datalogger, scale], ["date", "net_wt_lb"]).code == "SC-1"


def test_a_file_no_profile_fits_is_refused():
    with pytest.raises(ValidationError):
        choose_profile([profile()], ["something", "else"])


def test_two_profiles_that_both_fit_are_refused_rather_than_guessed_between():
    first = profile(code="DL-1")
    second = profile(code="DL-2")
    with pytest.raises(ValidationError) as excinfo:
        choose_profile([first, second], ["DateTime", "Temp_F"])
    assert "DL-1" in str(excinfo.value)


def test_a_row_is_renamed_without_being_converted():
    row = {"DateTime": "2025-03-01 06:00", "Temp_F": "50", "Extra": "x"}
    described = describe_row(profile(), row)
    assert described == {"taken_at": "2025-03-01 06:00", "temperature": "50"}
