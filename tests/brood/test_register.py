from decimal import Decimal

import pytest

from hatchlot.brood.eggcount import CountMethod, EggEstimate
from hatchlot.brood.female import BroodFemale, CullReason, Ripeness
from hatchlot.brood.register import (
    BroodRegister,
    check_take_against_register,
    summarise_season,
)
from hatchlot.brood.take import SpawnTake, TakeRegister
from hatchlot.calendar import DateRange
from hatchlot.errors import PolicyError, ValidationError
from hatchlot.quantities.base import Quantity
from hatchlot.quantities.temperature import Temperature

SEASON = DateRange("2024-09-01", "2024-11-30")


def female(tag, length="78", weight="5.4"):
    return BroodFemale(
        tag=tag, species="CHK", length=Quantity(length, "cm"), weight=Quantity(weight, "kg")
    )


def register_with(count=3):
    register = BroodRegister()
    for index in range(count):
        register.add(female(f"F-{index:03d}"))
    return register


def take_of(code, tags, day="2024-09-13", eggs=4500, release=True):
    entry = SpawnTake(
        code=code, day=day, species="CHK", water=Temperature(11, "C"), spawned_by="kt"
    )
    for tag in tags:
        entry.add_female(tag)
    entry.add_male("M-001")
    entry.close(EggEstimate(eggs, CountMethod.VON_BAYER))
    if release:
        entry.release("kt")
    return entry


def test_the_register_lists_what_is_still_available():
    register = register_with(3)
    register.get("F-000").cull("2024-09-10", CullReason.DISEASE, "kt")
    assert len(register.available()) == 2
    assert len(register.in_state(Ripeness.CULLED)) == 1
    assert [f.tag for f in register.culled_for(CullReason.DISEASE)] == ["F-000"]


def test_the_biomass_of_the_pen():
    register = register_with(2)
    assert register.biomass() == Quantity("10.8", "kg")
    assert BroodRegister().biomass() == Quantity(0, "kg")


def test_the_expected_eggs_counts_only_the_fish_still_in_the_run():
    register = register_with(3)
    full = register.expected_eggs()
    register.get("F-000").cull("2024-09-10", CullReason.SURPLUS, "kt")
    assert register.expected_eggs() < full


def test_the_handling_load_needs_somebody_to_have_been_handled():
    register = register_with(2)
    assert register.handling_load() == Decimal(0)
    register.get("F-000").check("2024-09-01", Ripeness.GREEN, "kt")
    register.get("F-000").check("2024-09-08", Ripeness.GREEN, "kt")
    assert register.handling_load() == Decimal(1)
    with pytest.raises(ValidationError):
        BroodRegister().handling_load()


def test_a_season_counts_only_the_releases_inside_its_window():
    takes = TakeRegister()
    takes.add(take_of("T-001", ["F-000", "F-001"]))
    takes.add(take_of("T-002", ["F-002"], day="2024-12-20"))
    summary = summarise_season(register_with(3), takes, SEASON, 5000)
    assert summary.takes_released == 1
    assert summary.females_spawned == 2
    assert summary.green_eggs == Decimal(4500)


def test_a_held_take_is_counted_but_its_eggs_are_not():
    takes = TakeRegister()
    takes.add(take_of("T-001", ["F-000"], release=False))
    summary = summarise_season(register_with(3), takes, SEASON, 5000)
    assert summary.takes_held == 1
    assert summary.green_eggs == Decimal(0)


def test_the_target_share_and_whether_it_was_met():
    takes = TakeRegister()
    takes.add(take_of("T-001", ["F-000", "F-001"], eggs=6000))
    summary = summarise_season(register_with(3), takes, SEASON, 5000)
    assert summary.target_share == Decimal("1.2")
    assert summary.is_target_met
    assert summary.eggs_per_female == Decimal(3000)


def test_a_season_that_took_nothing():
    summary = summarise_season(register_with(3), TakeRegister(), SEASON, 5000)
    assert summary.green_eggs == Decimal(0)
    assert summary.eggs_per_female == Decimal(0)
    assert not summary.is_target_met


def test_a_target_of_nothing_is_refused():
    with pytest.raises(ValidationError):
        summarise_season(register_with(3), TakeRegister(), SEASON, 0)


def test_the_cull_rate_over_the_pen():
    register = register_with(4)
    register.get("F-000").cull("2024-09-10", CullReason.DISEASE, "kt")
    summary = summarise_season(register, TakeRegister(), SEASON, 5000)
    assert summary.cull_rate == Decimal("0.25")
    assert summarise_season(BroodRegister(), TakeRegister(), SEASON, 5000).cull_rate == Decimal(0)


def test_the_season_line_reads_like_a_report_heading():
    takes = TakeRegister()
    takes.add(take_of("T-001", ["F-000", "F-001"]))
    line = summarise_season(register_with(3), takes, SEASON, 5000).line()
    assert "2 spawned" in line
    assert "90% of target" in line


def test_a_take_naming_a_fish_the_register_never_had_is_refused():
    takes = take_of("T-001", ["F-000", "F-099"])
    with pytest.raises(PolicyError) as excinfo:
        check_take_against_register(takes, register_with(3))
    assert excinfo.value.rule == "take.unknown_female"


def test_a_take_naming_a_culled_fish_is_refused():
    register = register_with(3)
    register.get("F-000").cull("2024-09-10", CullReason.DISEASE, "kt")
    with pytest.raises(PolicyError) as excinfo:
        check_take_against_register(take_of("T-001", ["F-000"]), register)
    assert excinfo.value.rule == "take.culled_female"


def test_a_take_that_matches_the_register_passes_quietly():
    check_take_against_register(take_of("T-001", ["F-000"]), register_with(3))
