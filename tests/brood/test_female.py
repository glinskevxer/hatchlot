from datetime import date
from decimal import Decimal

import pytest

from hatchlot.brood.female import (
    BroodFemale,
    CullReason,
    Ripeness,
    mean_condition,
    parse_length,
    sort_by_size,
    total_weight,
)
from hatchlot.errors import StateError, ValidationError
from hatchlot.numeric import quantize
from hatchlot.quantities.base import Quantity


def female(tag="F-001", length="78", weight="5.4"):
    return BroodFemale(
        tag=tag,
        species="CHK",
        length=Quantity(length, "cm"),
        weight=Quantity(weight, "kg"),
    )


def test_a_female_normalises_her_tag_and_starts_green():
    fish = female(tag=" f 001 ")
    assert fish.tag == "F-001"
    assert fish.ripeness is Ripeness.GREEN
    assert fish.is_available


def test_a_fish_of_no_length_or_no_weight_is_refused():
    with pytest.raises(ValidationError):
        female(length="0")
    with pytest.raises(ValidationError):
        female(weight="0")


def test_a_female_with_no_origin_is_refused():
    with pytest.raises(ValidationError):
        BroodFemale(
            tag="F-1",
            species="CHK",
            length=Quantity(70, "cm"),
            weight=Quantity(4, "kg"),
            origin=" ",
        )


def test_the_condition_factor_is_fultons_k_on_grams_and_centimetres():
    fish = female(length="78", weight="5.4")
    assert quantize(fish.condition_factor, 3) == Decimal("1.138")


def test_a_check_that_finds_her_still_green_is_allowed_again_and_again():
    fish = female()
    fish.check("2024-09-01", Ripeness.GREEN, "kt")
    fish.check("2024-09-08", Ripeness.GREEN, "kt")
    assert fish.handling_count() == 2
    assert fish.ripeness is Ripeness.GREEN


def test_the_run_goes_green_then_ripe_then_spawned():
    fish = female()
    fish.check("2024-09-01", Ripeness.RIPE, "kt")
    fish.check("2024-09-01", Ripeness.SPAWNED, "kt")
    assert fish.ripeness is Ripeness.SPAWNED
    assert not fish.is_available
    assert fish.spawned_on() == date(2024, 9, 1)


def test_a_green_female_cannot_be_spawned_without_being_found_ripe():
    fish = female()
    with pytest.raises(StateError):
        fish.check("2024-09-01", Ripeness.SPAWNED, "kt")


def test_nothing_follows_a_terminal_state():
    fish = female()
    fish.check("2024-09-01", Ripeness.RIPE, "kt")
    fish.check("2024-09-02", Ripeness.SPAWNED, "kt")
    with pytest.raises(StateError):
        fish.check("2024-09-03", Ripeness.RIPE, "kt")


def test_a_check_cannot_be_dated_before_the_one_before_it():
    fish = female()
    fish.check("2024-09-08", Ripeness.GREEN, "kt")
    with pytest.raises(ValidationError):
        fish.check("2024-09-01", Ripeness.GREEN, "kt")


def test_a_check_needs_a_person_and_a_real_ripeness():
    fish = female()
    with pytest.raises(ValidationError):
        fish.check("2024-09-01", Ripeness.RIPE, "  ")
    with pytest.raises(ValidationError):
        fish.check("2024-09-01", "ripe", "kt")


def test_culling_puts_the_reason_on_the_record():
    fish = female()
    fish.cull("2024-09-01", CullReason.DISEASE, "kt")
    assert fish.ripeness is Ripeness.CULLED
    assert fish.cull_reason is CullReason.DISEASE
    assert fish.checks[-1].note == "disease"
    assert not fish.is_available


def test_a_cull_reason_that_is_not_one_is_refused():
    with pytest.raises(ValidationError):
        female().cull("2024-09-01", "sick", "kt")


def test_a_ripe_female_can_still_be_culled_overripe():
    fish = female()
    fish.check("2024-09-01", Ripeness.RIPE, "kt")
    fish.cull("2024-09-10", CullReason.OVERRIPE, "kt")
    assert fish.cull_reason is CullReason.OVERRIPE


def test_a_mortality_ends_the_record_from_either_state():
    fish = female()
    fish.check("2024-09-01", Ripeness.MORTALITY, "kt")
    assert fish.ripeness.is_terminal


def test_a_female_never_spawned_has_no_spawn_date():
    assert female().spawned_on() is None


def test_days_held_needs_two_checks():
    fish = female()
    assert fish.days_held() == 0
    fish.check("2024-09-01", Ripeness.GREEN, "kt")
    assert fish.days_held() == 0
    fish.check("2024-09-15", Ripeness.RIPE, "kt")
    assert fish.days_held() == 14


def test_the_mean_condition_of_a_group():
    group = [female(weight="5.4"), female(tag="F-002", weight="4.6")]
    assert mean_condition(group) > 0
    with pytest.raises(ValidationError):
        mean_condition([])


def test_a_crew_works_a_pen_largest_first_by_default():
    group = [female(tag="F-1", weight="4"), female(tag="F-2", weight="6")]
    assert [fish.tag for fish in sort_by_size(group)] == ["F-2", "F-1"]
    assert [fish.tag for fish in sort_by_size(group, largest_first=False)] == ["F-1", "F-2"]


def test_the_weight_of_a_group_adds_up():
    group = [female(weight="4"), female(tag="F-2", weight="6")]
    assert total_weight(group) == Quantity(10, "kg")
    assert total_weight([]) == Quantity(0, "kg")


def test_a_length_off_the_board_becomes_a_quantity():
    assert parse_length("78.5") == Quantity("78.5", "cm")
    assert parse_length(31, "in").symbol == "in"
    with pytest.raises(ValidationError):
        parse_length(0)
