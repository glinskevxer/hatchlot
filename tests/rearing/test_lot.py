from datetime import date
from decimal import Decimal

import pytest

from hatchlot.errors import StateError, ValidationError
from hatchlot.identifiers import LotCode
from hatchlot.numeric import quantize
from hatchlot.quantities.base import Quantity
from hatchlot.rearing.lot import (
    LotState,
    RearingLot,
    total_biomass,
    total_population,
    weighted_mean_weight,
)


def lot(sequence=1, population="50000", grams="2.5", container="RW-1"):
    return RearingLot(
        code=LotCode(2024, "CHK", sequence),
        container=container,
        ponded_on=date(2025, 1, 15),
        population=Decimal(population),
        mean_weight=Quantity(grams, "g"),
    )


def test_a_lot_normalises_its_container_and_starts_rearing():
    entry = lot(container=" rw 1 ")
    assert entry.container == "RW-1"
    assert entry.state is LotState.REARING


def test_a_lot_needs_a_lot_code_a_population_and_a_weight():
    with pytest.raises(ValidationError):
        RearingLot(
            code="2024-CHK-01",  # type: ignore[arg-type]
            container="RW-1",
            ponded_on=date(2025, 1, 15),
            population=Decimal(1),
            mean_weight=Quantity(1, "g"),
        )
    with pytest.raises(ValidationError):
        lot(population="0")
    with pytest.raises(ValidationError):
        lot(grams="0")


def test_the_biomass_is_the_population_times_the_mean_weight():
    assert lot(population="50000", grams="2.5").biomass == Quantity("125.000", "kg")


def test_fish_per_pound_is_what_the_crew_actually_says():
    assert quantize(lot(grams="2.5").fish_per_pound, 0) == Decimal(181)
    assert quantize(lot(grams="454").fish_per_pound, 2) == Decimal("1.00")


def test_the_length_comes_off_the_weight_through_the_species_factor():
    small = lot(grams="2.5").length
    big = lot(grams="20").length
    assert big > small
    assert quantize(small.to("in").amount, 2) == Decimal("2.40")
    assert quantize(small.to("cm").amount, 1) == Decimal("6.1")


def test_the_species_comes_off_the_lot_code():
    assert lot().species.code == "CHK"


def test_days_reared_and_the_refusal_of_a_day_before_ponding():
    entry = lot()
    assert entry.days_reared("2025-02-14") == 30
    with pytest.raises(ValidationError):
        entry.days_reared("2025-01-01")


def test_removing_fish_comes_off_the_population():
    entry = lot(population="50000")
    assert entry.remove(500) == Decimal(49500)
    with pytest.raises(ValidationError):
        entry.remove(60000)
    with pytest.raises(ValidationError):
        entry.remove(0)


def test_removing_everything_closes_the_lot():
    entry = lot(population="100")
    entry.remove(100)
    assert entry.state is LotState.RELEASED
    assert entry.state.is_closed
    with pytest.raises(StateError):
        entry.remove(1)


def test_removing_everything_for_a_reason_reads_as_a_loss():
    entry = lot(population="100")
    entry.remove(100, reason="pump failure overnight")
    assert entry.state is LotState.LOST
    assert entry.note == "pump failure overnight"


def test_adding_fish_without_a_weight_leaves_the_mean_alone():
    entry = lot(population="1000", grams="2")
    entry.add(1000)
    assert entry.population == Decimal(2000)
    assert entry.mean_weight == Quantity(2, "g")


def test_adding_fish_with_a_weight_blends_the_mean():
    entry = lot(population="1000", grams="2")
    entry.add(1000, Quantity(4, "g"))
    assert entry.mean_weight == Quantity(3, "g")


def test_adding_nothing_or_weightless_fish_is_refused():
    entry = lot()
    with pytest.raises(ValidationError):
        entry.add(0)
    with pytest.raises(ValidationError):
        entry.add(100, Quantity(0, "g"))


def test_a_sample_resizes_the_lot():
    entry = lot(grams="2")
    assert entry.resize(Quantity(3, "g")) == Quantity(3, "g")
    with pytest.raises(ValidationError):
        entry.resize(Quantity(0, "g"))


def test_a_lot_moves_between_containers_until_it_is_closed():
    entry = lot()
    assert entry.move_to(" rw 2 ") == "RW-2"
    entry.remove(entry.population)
    with pytest.raises(StateError):
        entry.move_to("RW-3")


def test_a_hold_stops_a_lot_and_can_be_lifted():
    entry = lot()
    entry.hold("treatment withdrawal")
    assert entry.state is LotState.HELD
    assert entry.note == "treatment withdrawal"
    entry.release_hold()
    assert entry.state.value == "rearing"
    assert entry.note == ""


def test_a_hold_needs_a_reason_and_a_lift_needs_a_hold():
    entry = lot()
    with pytest.raises(ValidationError):
        entry.hold("  ")
    with pytest.raises(StateError):
        entry.release_hold()


def test_a_closed_lot_cannot_be_held():
    entry = lot(population="10")
    entry.remove(10)
    with pytest.raises(StateError):
        entry.hold("treatment")


def test_marks_go_on_once():
    entry = lot()
    assert entry.add_mark(" ad clip ") == "AD-CLIP"
    with pytest.raises(ValidationError):
        entry.add_mark("AD-CLIP")


def test_totals_skip_the_closed_lots():
    first = lot(1, population="1000", grams="2")
    second = lot(2, population="1000", grams="4")
    closed = lot(3, population="1000")
    closed.remove(1000)
    lots = [first, second, closed]
    assert total_population(lots) == Decimal(2000)
    assert total_biomass(lots) == Quantity("6.000", "kg")
    assert weighted_mean_weight(lots) == Quantity(3, "g")


def test_averaging_with_no_live_lots_is_refused():
    closed = lot(population="10")
    closed.remove(10)
    with pytest.raises(ValidationError):
        weighted_mean_weight([closed])
    with pytest.raises(ValidationError):
        weighted_mean_weight([])


def test_a_closed_lot_can_be_rebuilt_with_no_fish_in_it():
    rebuilt = RearingLot(
        code=LotCode(2024, "CHK", 9),
        container="RW-1",
        ponded_on=date(2025, 1, 15),
        population=Decimal(0),
        mean_weight=Quantity(2, "g"),
        state=LotState.RELEASED,
    )
    assert rebuilt.population == Decimal(0)
    with pytest.raises(ValidationError):
        RearingLot(
            code=LotCode(2024, "CHK", 9),
            container="RW-1",
            ponded_on=date(2025, 1, 15),
            population=Decimal(0),
            mean_weight=Quantity(2, "g"),
        )
