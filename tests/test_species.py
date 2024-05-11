from decimal import Decimal

import pytest

from hatchlot.errors import NotFoundError, ValidationError
from hatchlot.species import all_species, anadromous_species, resolve_species, species


def test_a_species_carries_the_constants_the_engine_needs():
    chinook = species("chk")
    assert chinook.common_name == "chinook salmon"
    assert chinook.hatch_units == Decimal("850")
    assert chinook.anadromous


def test_an_unknown_code_is_a_not_found_not_a_crash():
    with pytest.raises(NotFoundError) as excinfo:
        species("XYZ")
    assert excinfo.value.kind == "species"


def test_a_code_of_the_wrong_shape_is_a_validation_error():
    with pytest.raises(ValidationError):
        species("chinook")


@pytest.mark.parametrize(
    ("text", "code"),
    [
        ("chinook", "CHK"),
        ("King salmon", "CHK"),
        ("coho", "COH"),
        ("silvers", "COH"),
        ("STH", "STH"),
        (" rbt ", "RBT"),
        ("brookie", "BKT"),
    ],
)
def test_the_names_a_crew_says_resolve_to_a_code(text, code):
    assert resolve_species(text).code == code


@pytest.mark.parametrize("bad", ["", "   ", "walleye"])
def test_a_species_the_station_does_not_run_is_refused(bad):
    with pytest.raises((ValidationError, NotFoundError)):
        resolve_species(bad)


def test_development_fraction_is_relative_to_hatch():
    chinook = species("CHK")
    assert chinook.development_fraction(425) == Decimal("0.5")
    assert chinook.development_fraction(850) == Decimal("1")


def test_development_fraction_keeps_counting_past_hatch():
    assert species("CHK").development_fraction(1700) == Decimal("2")


def test_the_rearing_band_is_closed_at_both_ends():
    trout = species("RBT")
    assert trout.is_within_rearing_band(Decimal("7"))
    assert trout.is_within_rearing_band(Decimal("16"))
    assert not trout.is_within_rearing_band(Decimal("6.9"))
    assert not trout.is_within_rearing_band(Decimal("16.1"))


def test_every_species_has_a_sane_ordering_of_its_development_marks():
    for entry in all_species():
        assert entry.eye_up_units < entry.hatch_units < entry.swim_up_units


def test_every_species_has_a_lethal_temperature_above_its_rearing_band():
    for entry in all_species():
        assert entry.rearing_low_c < entry.rearing_high_c < entry.lethal_high_c


def test_the_table_is_returned_in_code_order():
    codes = [entry.code for entry in all_species()]
    assert codes == sorted(codes)
    assert len(codes) == 9


def test_the_anadromous_subset_is_a_subset():
    runs = anadromous_species()
    assert {entry.code for entry in runs} == {"CHK", "COH", "CHM", "STH", "ATS"}
    assert set(runs).issubset(set(all_species()))
