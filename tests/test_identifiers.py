import pytest

from hatchlot.errors import ValidationError
from hatchlot.identifiers import (
    LotCode,
    brood_year,
    is_split_of,
    normalise_code,
    normalise_species,
    split_suffix,
)


@pytest.mark.parametrize(
    "raw",
    ["rw-3", " RW 3 ", "rw_3", "RW.3", "rw/3", "RW--3", "-rw-3-"],
)
def test_every_way_a_container_gets_written_lands_on_one_key(raw):
    assert normalise_code(raw) == "RW-3"


@pytest.mark.parametrize("bad", ["", "   ", "-", "rw#3", "rw 3!", "a" * 30, 7, None])
def test_junk_is_refused_as_a_code(bad):
    with pytest.raises(ValidationError):
        normalise_code(bad)


def test_species_codes_are_three_letters():
    assert normalise_species(" chk ") == "CHK"
    with pytest.raises(ValidationError):
        normalise_species("CHIN")
    with pytest.raises(ValidationError):
        normalise_species("CH1")


def test_brood_year_takes_text_or_a_number():
    assert brood_year("2024") == 2024
    assert brood_year(2024) == 2024


@pytest.mark.parametrize("bad", ["twenty", "1800", "3100", None, ""])
def test_an_implausible_brood_year_is_refused(bad):
    with pytest.raises(ValidationError):
        brood_year(bad)


def test_a_lot_code_prints_the_way_it_is_written_on_the_tray():
    assert str(LotCode(2024, "chk", 1)) == "2024-CHK-01"


def test_a_lot_code_parses_back_from_its_own_printing():
    assert LotCode.parse("2024-CHK-01") == LotCode(2024, "CHK", 1)


def test_a_lot_code_parses_from_the_sloppy_form():
    assert LotCode.parse(" 2024 chk 1 ") == LotCode(2024, "CHK", 1)


@pytest.mark.parametrize("bad", ["2024-CHK", "2024-CHK-01-A", "abc"])
def test_a_lot_code_needs_all_three_parts(bad):
    with pytest.raises(ValidationError):
        LotCode.parse(bad)


@pytest.mark.parametrize("bad", [0, 1000, "x", None])
def test_a_lot_sequence_out_of_range_is_refused(bad):
    with pytest.raises(ValidationError):
        LotCode(2024, "CHK", bad)


def test_lots_sort_by_their_parts_not_by_their_text():
    lots = [LotCode(2024, "CHK", 10), LotCode(2024, "CHK", 2), LotCode(2023, "RBT", 9)]
    assert [str(lot) for lot in sorted(lots)] == ["2023-RBT-09", "2024-CHK-02", "2024-CHK-10"]


def test_the_successor_is_the_next_sequence_in_the_same_year():
    assert str(LotCode(2024, "CHK", 1).successor()) == "2024-CHK-02"


def test_a_split_hangs_a_suffix_off_the_parent():
    assert split_suffix("2024-CHK-01", "a") == "2024-CHK-01A"


def test_a_split_suffix_is_short():
    with pytest.raises(ValidationError):
        split_suffix("2024-CHK-01", "abcd")


def test_a_child_knows_its_parent_and_a_stranger_does_not():
    assert is_split_of("2024-CHK-01A", "2024-CHK-01")
    assert not is_split_of("2024-CHK-01", "2024-CHK-01")
    assert not is_split_of("2024-CHK-02", "2024-CHK-01")
