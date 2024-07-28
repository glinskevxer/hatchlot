from decimal import Decimal

import pytest

from hatchlot.brood.cross import Family
from hatchlot.brood.pedigree import (
    Pedigree,
    effective_population,
    inbreeding_rate,
    variance_effective_population,
)
from hatchlot.errors import PolicyError, ValidationError
from hatchlot.numeric import quantize


def test_an_even_sex_ratio_gives_an_effective_size_equal_to_the_parents():
    assert effective_population(10, 10) == Decimal(20)


def test_a_lopsided_ratio_costs_far_more_than_it_looks():
    assert quantize(effective_population(1, 10), 2) == Decimal("3.64")


@pytest.mark.parametrize(("males", "females"), [(0, 10), (10, 0), (-1, 10)])
def test_a_run_missing_a_sex_has_no_effective_size(males, females):
    with pytest.raises(ValidationError):
        effective_population(males, females)


def test_the_inbreeding_rate_falls_as_the_effective_size_rises():
    assert inbreeding_rate(50) == Decimal("0.01")
    assert inbreeding_rate(100) < inbreeding_rate(50)


def test_an_effective_size_of_nothing_is_refused():
    with pytest.raises(ValidationError):
        inbreeding_rate(0)


def test_even_families_give_back_about_the_number_of_parents():
    assert quantize(variance_effective_population([100, 100, 100, 100]), 2) == Decimal("4.03")


def test_uneven_families_pull_the_effective_size_down():
    even = variance_effective_population([100, 100, 100, 100])
    uneven = variance_effective_population([370, 10, 10, 10])
    assert uneven < even


def test_a_variance_needs_two_families_and_some_offspring():
    with pytest.raises(ValidationError):
        variance_effective_population([100])
    with pytest.raises(ValidationError):
        variance_effective_population([0, 0])


def test_a_negative_family_size_is_refused():
    with pytest.raises(ValidationError):
        variance_effective_population([100, -1])


def test_two_families_of_one_cannot_support_the_estimate():
    with pytest.raises(ValidationError):
        variance_effective_population([1, 1])


def build():
    tree = Pedigree()
    tree.record("J-1", Family("F-1", "M-1"))
    tree.record("J-2", Family("F-1", "M-1"))
    tree.record("J-3", Family("F-2", "M-2"))
    return tree


def test_a_fish_is_filed_once_against_one_family():
    tree = build()
    family = tree.family_of("j 1")
    assert family is not None
    assert family.dam == "F-1"
    with pytest.raises(ValidationError):
        tree.record("J-1", Family("F-3", "M-3"))


def test_a_fish_cannot_be_its_own_parent():
    tree = Pedigree()
    with pytest.raises(ValidationError):
        tree.record("F-1", Family("F-1", "M-1"))


def test_a_fish_with_nothing_on_file_has_no_family():
    assert Pedigree().family_of("J-9") is None


def test_ancestors_walk_back_as_far_as_they_are_asked_to():
    tree = build()
    tree.record("F-1", Family("F-0", "M-0"))
    assert tree.ancestors("J-1", generations=1) == {"F-1", "M-1"}
    assert tree.ancestors("J-1", generations=2) == {"F-1", "M-1", "F-0", "M-0"}


def test_looking_back_no_generations_is_not_a_question():
    with pytest.raises(ValidationError):
        build().ancestors("J-1", generations=0)


def test_full_sibs_are_spotted_and_half_strangers_are_not():
    tree = build()
    assert tree.are_full_sibs("J-1", "J-2")
    assert not tree.are_full_sibs("J-1", "J-3")
    assert not tree.are_full_sibs("J-1", "J-9")


def test_relatedness_is_the_share_of_known_ancestors_in_common():
    tree = build()
    assert tree.relatedness("J-1", "J-2") == Decimal(1)
    assert tree.relatedness("J-1", "J-3") == Decimal(0)


def test_a_fish_with_no_ancestry_is_related_to_nobody():
    assert build().relatedness("J-1", "J-9") == Decimal(0)


def test_a_half_sib_pair_shares_half_its_ancestry():
    tree = Pedigree()
    tree.record("J-1", Family("F-1", "M-1"))
    tree.record("J-2", Family("F-2", "M-1"))
    assert tree.relatedness("J-1", "J-2") == Decimal("0.5")


def test_a_full_sib_mating_is_refused_by_name():
    tree = build()
    with pytest.raises(PolicyError) as excinfo:
        tree.check_mating("J-1", "J-2")
    assert excinfo.value.rule == "pedigree.full_sibs"


def test_a_too_close_mating_is_refused_on_shared_ancestry():
    tree = Pedigree()
    tree.record("J-1", Family("F-1", "M-1"))
    tree.record("J-2", Family("F-2", "M-1"))
    with pytest.raises(PolicyError) as excinfo:
        tree.check_mating("J-1", "J-2", limit="0.4")
    assert excinfo.value.rule == "pedigree.relatedness"


def test_an_unrelated_mating_passes_quietly():
    tree = build()
    assert tree.check_mating("J-1", "J-3") is None


def test_the_contributions_count_both_sides_of_every_family():
    counts = build().contributions()
    assert counts["F-1"] == 2
    assert counts["M-2"] == 1


def test_the_census_reads_the_effective_size_off_the_file():
    assert build().census() == Decimal(4)
