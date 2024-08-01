from decimal import Decimal

import pytest

from hatchlot.brood import BroodRegister, CrossDesign, Family, Pedigree, Ripeness, plan_day
from hatchlot.brood.female import BroodFemale
from hatchlot.brood.shed import ripe_females
from hatchlot.errors import PolicyError, ValidationError
from hatchlot.quantities.base import Quantity


def register_with(ripe=("F-001", "F-002"), green=("F-003",), weights=None):
    register = BroodRegister()
    sizes = weights or {}
    for tag in list(ripe) + list(green):
        register.add(
            BroodFemale(
                tag=tag,
                species="CHK",
                length=Quantity(78, "cm"),
                weight=Quantity(sizes.get(tag, "5.4"), "kg"),
            )
        )
    for tag in ripe:
        register.get(tag).check("2024-09-13", Ripeness.RIPE, "kt")
    return register


def test_only_the_ripe_hens_are_offered_and_the_biggest_comes_first():
    register = register_with(weights={"F-001": "4.0", "F-002": "6.0"})
    assert [hen.tag for hen in ripe_females(register)] == ["F-002", "F-001"]


def test_a_day_with_nothing_ripe_is_refused():
    with pytest.raises(ValidationError):
        plan_day(register_with(ripe=()), ["M-1"])


def test_a_day_with_no_males_is_refused():
    with pytest.raises(ValidationError):
        plan_day(register_with(), [])


def test_a_factorial_day_crosses_every_ripe_hen_against_every_male():
    plan = plan_day(register_with(), ["M-1", "M-2"])
    assert plan.cross.family_count == 4
    assert len(plan.dams) == 2
    assert plan.refused_hens == ()
    assert plan.refused_pairings == ()


def test_a_pairwise_day_trims_both_sides_to_the_shorter_one():
    plan = plan_day(register_with(), ["M-1", "M-2", "M-3"], design=CrossDesign.PAIRWISE)
    assert plan.cross.family_count == 2


def test_a_forbidden_pairing_is_dropped_while_the_hen_stays_in_the_day():
    tree = Pedigree()
    tree.record("F-001", Family("D-1", "S-1"))
    tree.record("M-1", Family("D-1", "S-1"))
    plan = plan_day(register_with(), ["M-1", "M-2"], pedigree=tree)
    assert plan.refused_hens == ()
    assert plan.refused_pairings == ("F-001xM-1",)
    assert plan.cross.family_count == 3


def test_a_hen_too_close_to_every_male_is_dropped_from_the_day():
    tree = Pedigree()
    tree.record("F-001", Family("D-1", "S-1"))
    tree.record("M-1", Family("D-1", "S-1"))
    tree.record("M-2", Family("D-1", "S-1"))
    plan = plan_day(register_with(), ["M-1", "M-2"], pedigree=tree)
    assert plan.refused_hens == ("F-001",)
    assert [hen.tag for hen in plan.dams] == ["F-002"]


def test_a_day_where_every_pairing_is_forbidden_is_refused_by_name():
    tree = Pedigree()
    for tag in ("F-001", "F-002", "M-1"):
        tree.record(tag, Family("D-1", "S-1"))
    with pytest.raises(PolicyError) as excinfo:
        plan_day(register_with(), ["M-1"], pedigree=tree)
    assert excinfo.value.rule == "shed.no_pairings"


def test_the_expected_eggs_come_off_the_fecundity_curve():
    plan = plan_day(register_with(), ["M-1", "M-2"], target_eggs=20000)
    assert plan.expected_eggs > Decimal(10000)
    assert plan.shortfall > 0
    assert not plan.meets_target


def test_a_day_that_makes_its_number_has_no_shortfall():
    plan = plan_day(register_with(), ["M-1", "M-2"], target_eggs=1000)
    assert plan.meets_target
    assert plan.shortfall == Decimal(0)


def test_a_target_of_nothing_is_refused():
    with pytest.raises(ValidationError):
        plan_day(register_with(), ["M-1"], target_eggs=0)


def test_a_day_that_leans_on_one_male_is_still_refused_by_the_cross_rule():
    register = register_with(ripe=("F-001", "F-002", "F-003"), green=())
    with pytest.raises(PolicyError) as excinfo:
        plan_day(register, ["M-1"])
    assert excinfo.value.rule == "cross.sire_share"


def test_the_day_line_says_what_the_crew_is_in_for():
    line = plan_day(register_with(), ["M-1", "M-2"], target_eggs=20000).line()
    assert "2 hens" in line
    assert "4 families" in line
