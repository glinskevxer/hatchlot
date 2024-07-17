from datetime import date
from decimal import Decimal

import pytest

from hatchlot.brood.eggcount import CountMethod, EggEstimate
from hatchlot.brood.take import SpawnTake, TakeRegister, TakeState, enumerate_take
from hatchlot.calendar import DateRange
from hatchlot.errors import DuplicateError, NotFoundError, StateError, ValidationError
from hatchlot.quantities.temperature import Temperature


def take(code="T-001", day="2024-09-13", species="CHK"):
    return SpawnTake(
        code=code,
        day=day,
        species=species,
        water=Temperature(11, "C"),
        spawned_by="kt",
    )


def stocked(code="T-001", day="2024-09-13", females=3, species="CHK"):
    entry = take(code=code, day=day, species=species)
    for index in range(females):
        entry.add_female(f"F-{index:03d}")
    entry.add_male("M-001")
    return entry


def test_a_take_normalises_its_code_species_and_day():
    entry = take(code=" t 001 ", species="chk")
    assert entry.code == "T-001"
    assert entry.species == "CHK"
    assert entry.day == date(2024, 9, 13)
    assert entry.state is TakeState.OPEN


def test_a_take_needs_whoever_ran_it():
    with pytest.raises(ValidationError):
        SpawnTake(
            code="T-1",
            day=date(2024, 9, 13),
            species="CHK",
            water=Temperature(11, "C"),
            spawned_by=" ",
        )


def test_the_same_fish_cannot_go_on_a_take_twice():
    entry = take()
    entry.add_female("F-001")
    with pytest.raises(DuplicateError):
        entry.add_female("f 001")
    entry.add_male("M-001")
    with pytest.raises(DuplicateError):
        entry.add_male("M-001")


def test_a_take_with_no_females_or_no_males_cannot_close():
    entry = take()
    estimate = EggEstimate(4000, CountMethod.VON_BAYER)
    with pytest.raises(StateError):
        entry.close(estimate)
    entry.add_female("F-001")
    with pytest.raises(StateError):
        entry.close(estimate)


def test_closing_a_take_holds_it_rather_than_finishing_it():
    entry = stocked()
    entry.close(EggEstimate(4500, CountMethod.VON_BAYER))
    assert entry.state is TakeState.HELD
    assert not entry.is_finished
    assert entry.green_eggs == Decimal(4500)


def test_a_closed_take_takes_no_more_fish():
    entry = stocked()
    entry.close(EggEstimate(4500, CountMethod.VON_BAYER))
    with pytest.raises(StateError):
        entry.add_female("F-099")
    with pytest.raises(StateError):
        entry.add_male("M-099")


def test_a_take_closes_only_once_and_only_on_an_estimate():
    entry = stocked()
    entry.close(EggEstimate(4500, CountMethod.VON_BAYER))
    with pytest.raises(StateError):
        entry.close(EggEstimate(4500, CountMethod.VON_BAYER))
    other = stocked(code="T-002")
    with pytest.raises(ValidationError):
        other.close(4500)


def test_release_needs_a_name_and_a_held_take():
    entry = stocked()
    with pytest.raises(StateError):
        entry.release("kt")
    entry.close(EggEstimate(4500, CountMethod.VON_BAYER))
    with pytest.raises(ValidationError):
        entry.release("  ")
    entry.release(" kt ")
    assert entry.state is TakeState.RELEASED
    assert entry.released_by == "kt"
    assert entry.is_finished


def test_a_take_can_be_written_off_before_it_goes_to_incubation():
    entry = stocked()
    entry.close(EggEstimate(4500, CountMethod.VON_BAYER))
    entry.destroy("failed the screen")
    assert entry.state is TakeState.DESTROYED
    assert entry.note == "failed the screen"


def test_a_released_take_cannot_be_written_off_and_a_write_off_needs_a_reason():
    entry = stocked()
    entry.close(EggEstimate(4500, CountMethod.VON_BAYER))
    other = stocked(code="T-002")
    other.close(EggEstimate(4500, CountMethod.VON_BAYER))
    with pytest.raises(ValidationError):
        other.destroy(" ")
    entry.release("kt")
    with pytest.raises(StateError):
        entry.destroy("changed my mind")


def test_eggs_per_female_and_the_refusal_when_there_are_none():
    entry = stocked(females=3)
    entry.close(EggEstimate(4500, CountMethod.VON_BAYER))
    assert entry.eggs_per_female == Decimal(1500)
    with pytest.raises(ValidationError):
        assert take().eggs_per_female


def test_an_open_take_has_no_eggs_yet():
    assert take().green_eggs == Decimal(0)


def test_a_hand_counted_take_closes_in_one_call():
    entry = stocked()
    estimate = enumerate_take(entry, 3200)
    assert estimate.method is CountMethod.ENUMERATED
    assert entry.state is TakeState.HELD


def register_with(*takes):
    register = TakeRegister()
    for entry in takes:
        register.add(entry)
    return register


def test_the_register_refuses_two_takes_on_one_code():
    register = register_with(take())
    with pytest.raises(DuplicateError):
        register.add(take())


def test_the_register_looks_up_and_refuses_an_unknown_take():
    register = register_with(take())
    assert register.get(" t 001 ").code == "T-001"
    with pytest.raises(NotFoundError):
        register.get("T-999")


def test_the_register_orders_by_day_then_code():
    register = register_with(
        take(code="T-002", day="2024-09-20"),
        take(code="T-001", day="2024-09-13"),
    )
    assert [entry.code for entry in register.all()] == ["T-001", "T-002"]
    assert len(register) == 2


def test_the_register_slices_by_window_species_and_state():
    register = register_with(
        stocked(code="T-001", day="2024-09-13", species="CHK"),
        stocked(code="T-002", day="2024-10-20", species="COH"),
    )
    assert len(register.within(DateRange("2024-09-01", "2024-09-30"))) == 1
    assert len(register.for_species("coho")) == 1
    assert len(register.in_state(TakeState.OPEN)) == 2


def test_only_released_takes_count_toward_the_season_s_eggs():
    first = stocked(code="T-001")
    first.close(EggEstimate(4500, CountMethod.VON_BAYER))
    second = stocked(code="T-002", species="COH")
    second.close(EggEstimate(3000, CountMethod.VON_BAYER))
    register = register_with(first, second)
    assert register.green_eggs() == Decimal(0)
    first.release("kt")
    assert register.green_eggs() == Decimal(4500)
    second.release("kt")
    assert register.green_eggs("CHK") == Decimal(4500)
    assert register.green_eggs() == Decimal(7500)


def test_the_held_list_is_what_runs_the_shed():
    first = stocked(code="T-001")
    first.close(EggEstimate(4500, CountMethod.VON_BAYER))
    register = register_with(first, stocked(code="T-002"))
    assert [entry.code for entry in register.held()] == ["T-001"]


def test_the_females_used_across_a_season():
    register = register_with(stocked(females=3), stocked(code="T-002", females=2))
    assert register.females_used() == 5
