from datetime import date
from decimal import Decimal

import pytest

from hatchlot.errors import PolicyError, StateError, ValidationError
from hatchlot.identifiers import LotCode
from hatchlot.incubation.eggslot import EggLot, EggStage, LossCause
from hatchlot.incubation.shock import (
    expected_whites,
    fertility,
    is_shock_plausible,
    shock,
)
from hatchlot.species import species

CHINOOK = species("CHK")


def lot(green="10000"):
    return EggLot(
        code=LotCode(2024, "CHK", 1),
        take="T-001",
        species="CHK",
        spawned_on=date(2024, 9, 13),
        green_count=Decimal(green),
    )


def test_a_shock_leaves_the_eyed_count_standing_and_books_the_whites():
    eggs = lot()
    result = shock(eggs, "2024-10-25", 9000, CHINOOK, 430)
    assert eggs.count == Decimal(9000)
    assert eggs.stage is EggStage.EYED
    assert eggs.lost_to(LossCause.SHOCK) == Decimal(1000)
    assert result.whites == Decimal(1000)


def test_the_eye_up_rate_is_against_what_was_standing_at_the_shock():
    eggs = lot()
    eggs.record_loss("2024-09-20", 1000, LossCause.UNFERTILISED)
    result = shock(eggs, "2024-10-25", 8100, CHINOOK, 430)
    assert result.before == Decimal(9000)
    assert result.eye_up_rate == Decimal("0.9")
    assert result.white_rate == Decimal("0.1")


def test_shocking_before_eye_up_is_refused_by_name():
    with pytest.raises(PolicyError) as excinfo:
        shock(lot(), "2024-10-01", 9000, CHINOOK, 300)
    assert excinfo.value.rule == "incubation.tender"


def test_shocking_just_short_of_eye_up_is_refused_as_too_early():
    eggs = lot()
    with pytest.raises(PolicyError) as excinfo:
        shock(eggs, "2024-10-01", 9000, CHINOOK, 20)
    assert excinfo.value.rule == "incubation.shock_too_early"


def test_a_lot_is_shocked_once():
    eggs = lot()
    shock(eggs, "2024-10-25", 9000, CHINOOK, 430)
    with pytest.raises(StateError):
        shock(eggs, "2024-10-26", 8000, CHINOOK, 440)


def test_an_eyed_count_above_what_is_standing_is_refused():
    with pytest.raises(ValidationError):
        shock(lot(green="1000"), "2024-10-25", 1200, CHINOOK, 430)


def test_a_negative_eyed_count_is_refused():
    with pytest.raises(ValidationError):
        shock(lot(), "2024-10-25", -1, CHINOOK, 430)


def test_a_shock_that_lost_nothing_books_no_whites():
    eggs = lot(green="1000")
    result = shock(eggs, "2024-10-25", 1000, CHINOOK, 430)
    assert result.whites == Decimal(0)
    assert eggs.losses == []


def test_fertility_is_against_the_green_count_not_the_standing_one():
    eggs = lot(green="10000")
    eggs.record_loss("2024-09-20", 2000, LossCause.FUNGUS)
    result = shock(eggs, "2024-10-25", 7200, CHINOOK, 430)
    assert result.eye_up_rate == Decimal("0.9")
    assert fertility(result, 10000) == Decimal("0.72")


def test_fertility_against_no_green_count_is_refused():
    result = shock(lot(), "2024-10-25", 9000, CHINOOK, 430)
    with pytest.raises(ValidationError):
        fertility(result, 0)


def test_the_whites_a_normal_shock_should_give():
    assert expected_whites(10000) == Decimal(1000)
    assert expected_whites(10000, "0.95") == Decimal(500)


def test_an_impossible_expected_fertility_is_refused():
    with pytest.raises(ValidationError):
        expected_whites(10000, "1.5")
    with pytest.raises(ValidationError):
        expected_whites(0)


def test_a_believable_shock_and_one_that_wants_a_recount():
    good = shock(lot(), "2024-10-25", 9000, CHINOOK, 430)
    assert is_shock_plausible(good, 10000)
    poor = shock(lot(), "2024-10-25", 3000, CHINOOK, 430)
    assert not is_shock_plausible(poor, 10000)
    assert is_shock_plausible(poor, 10000, floor="0.2")
