from decimal import Decimal

import pytest

from hatchlot.brood.cross import CrossDesign, Family, merge_plans, plan_cross
from hatchlot.errors import DuplicateError, PolicyError, ValidationError


def test_a_family_normalises_both_parents_and_prints_its_identity():
    family = Family(" f 001 ", "m-001")
    assert family.dam == "F-001"
    assert family.identifier == "F-001xM-001"


def test_a_fish_cannot_be_crossed_with_itself():
    with pytest.raises(ValidationError):
        Family("F-001", "f 001")


def test_families_sort_by_dam_then_sire():
    families = [Family("F-002", "M-001"), Family("F-001", "M-002"), Family("F-001", "M-001")]
    assert [f.identifier for f in sorted(families)][0] == "F-001xM-001"


def test_a_pairwise_cross_makes_one_family_per_pair():
    plan = plan_cross(CrossDesign.PAIRWISE, ["F-1", "F-2"], ["M-1", "M-2"])
    assert plan.family_count == 2
    assert [f.identifier for f in plan.families] == ["F-1xM-1", "F-2xM-2"]


def test_a_pairwise_cross_needs_the_sides_to_match():
    with pytest.raises(ValidationError):
        plan_cross(CrossDesign.PAIRWISE, ["F-1", "F-2"], ["M-1"])


def test_a_factorial_cross_makes_every_combination():
    plan = plan_cross(CrossDesign.FACTORIAL, ["F-1", "F-2"], ["M-1", "M-2"])
    assert plan.family_count == 4
    assert plan.sire_load() == {"M-1": 2, "M-2": 2}
    assert plan.dam_load() == {"F-1": 2, "F-2": 2}


def test_a_pooled_cross_keeps_no_pedigree_and_says_so():
    plan = plan_cross(CrossDesign.POOLED, ["F-1", "F-2"], ["M-1", "M-2"])
    assert not plan.design.keeps_pedigree
    assert plan.family_count == 2
    assert all(family.sire.startswith("POOLED-") for family in plan.families)


def test_an_empty_side_is_refused():
    with pytest.raises(ValidationError):
        plan_cross(CrossDesign.FACTORIAL, [], ["M-1"])
    with pytest.raises(ValidationError):
        plan_cross(CrossDesign.FACTORIAL, ["F-1"], [])


def test_the_same_fish_twice_on_one_side_is_refused():
    with pytest.raises(DuplicateError):
        plan_cross(CrossDesign.FACTORIAL, ["F-1", "f 1"], ["M-1"])


def test_a_fish_on_both_sides_is_refused():
    with pytest.raises(ValidationError):
        plan_cross(CrossDesign.FACTORIAL, ["F-1"], ["F-1", "M-1"])


def test_a_design_that_is_not_a_design_is_refused():
    with pytest.raises(ValidationError):
        plan_cross("factorial", ["F-1"], ["M-1"])  # type: ignore[arg-type]


def test_one_male_over_his_share_is_refused_before_the_crew_starts():
    with pytest.raises(PolicyError) as excinfo:
        plan_cross(CrossDesign.FACTORIAL, ["F-1", "F-2", "F-3"], ["M-1"])
    assert excinfo.value.rule == "cross.sire_share"


def test_the_share_limit_can_be_relaxed_deliberately():
    plan = plan_cross(CrossDesign.FACTORIAL, ["F-1", "F-2"], ["M-1"], max_sire_share=1)
    assert plan.busiest_sire_share() == Decimal(1)


def test_a_pooled_cross_is_not_judged_on_sire_share():
    plan = plan_cross(CrossDesign.POOLED, ["F-1", "F-2", "F-3"], ["M-1"])
    assert plan.family_count == 3


def test_a_relaxed_share_still_has_to_be_a_positive_fraction():
    with pytest.raises(ValidationError):
        plan_cross(CrossDesign.PAIRWISE, ["F-1"], ["M-1"], max_sire_share=0)


def test_the_families_a_single_fish_appears_in():
    plan = plan_cross(CrossDesign.FACTORIAL, ["F-1", "F-2"], ["M-1", "M-2"])
    assert len(plan.families_of("M-1")) == 2
    assert len(plan.families_of("F-1")) == 2
    assert plan.families_of("M-9") == ()


def test_a_single_family_block_is_not_judged_on_a_share_of_itself():
    plan = plan_cross(CrossDesign.PAIRWISE, ["F-1"], ["M-1"])
    assert plan.busiest_sire_share() == Decimal(1)
    assert plan.family_count == 1


def test_merging_blocks_is_what_the_share_should_really_be_judged_on():
    first = plan_cross(CrossDesign.FACTORIAL, ["F-1", "F-2"], ["M-1", "M-2"])
    second = plan_cross(CrossDesign.FACTORIAL, ["F-3", "F-4"], ["M-1", "M-3"])
    merged = merge_plans([first, second])
    assert merged.family_count == 8
    assert merged.sire_load()["M-1"] == 4
    assert merged.busiest_sire_share() == Decimal("0.5")


def test_merging_nothing_or_mixed_designs_is_refused():
    with pytest.raises(ValidationError):
        merge_plans([])
    pairwise = plan_cross(CrossDesign.PAIRWISE, ["F-1"], ["M-1"])
    factorial = plan_cross(CrossDesign.FACTORIAL, ["F-2"], ["M-2"])
    with pytest.raises(ValidationError):
        merge_plans([pairwise, factorial])


def test_two_blocks_that_repeat_a_family_are_refused():
    block = plan_cross(CrossDesign.FACTORIAL, ["F-1"], ["M-1"])
    with pytest.raises(ValidationError):
        merge_plans([block, block])
