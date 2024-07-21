from decimal import Decimal

import pytest

from hatchlot.brood.screening import (
    Assay,
    AssayLevel,
    Disposition,
    Pathogen,
    Screen,
    band,
    disposition,
)
from hatchlot.errors import DuplicateError, ValidationError


def test_the_optical_density_bands():
    assert band("0.05") is AssayLevel.NEGATIVE
    assert band("0.10") is AssayLevel.LOW
    assert band("0.25") is AssayLevel.MODERATE
    assert band("0.90") is AssayLevel.HIGH


def test_a_negative_density_is_refused():
    with pytest.raises(ValidationError):
        band("-0.1")


def test_the_levels_rank_in_the_order_they_get_worse():
    ranks = [level.rank for level in (AssayLevel.NEGATIVE, AssayLevel.LOW, AssayLevel.MODERATE)]
    assert ranks == sorted(ranks)
    assert AssayLevel.PENDING.rank < AssayLevel.NEGATIVE.rank
    assert not AssayLevel.NEGATIVE.is_positive
    assert AssayLevel.LOW.is_positive


def test_the_pathogens_that_ride_inside_the_egg():
    assert Pathogen.IHNV.is_vertically_transmitted
    assert Pathogen.BKD.is_vertically_transmitted
    assert not Pathogen.WHIRLING.is_vertically_transmitted


def test_an_assay_normalises_its_tag_and_can_come_from_a_density():
    assay = Assay.from_density(" f 001 ", Pathogen.BKD, "0.30")
    assert assay.tag == "F-001"
    assert assay.level is AssayLevel.MODERATE


def test_an_assay_of_something_that_is_not_a_pathogen_is_refused():
    with pytest.raises(ValidationError):
        Assay(tag="F-1", pathogen="bkd", level=AssayLevel.LOW)  # type: ignore[arg-type]
    with pytest.raises(ValidationError):
        Assay(tag="F-1", pathogen=Pathogen.BKD, level="low")  # type: ignore[arg-type]


def screen(pathogens=(Pathogen.BKD,), females=4):
    return Screen(take="T-001", pathogens=tuple(pathogens), females_spawned=females)


def test_a_screen_that_looks_for_nothing_is_refused():
    with pytest.raises(ValidationError):
        Screen(take="T-1", pathogens=())


def test_a_take_cannot_spawn_a_negative_number_of_females():
    with pytest.raises(ValidationError):
        Screen(take="T-1", pathogens=(Pathogen.BKD,), females_spawned=-1)


def test_a_result_for_a_pathogen_not_on_the_screen_is_refused():
    sheet = screen()
    with pytest.raises(ValidationError):
        sheet.record(Assay.from_density("F-1", Pathogen.IHNV, "0.05"))


def test_the_same_fish_cannot_be_filed_twice_for_one_pathogen():
    sheet = screen()
    sheet.record(Assay.from_density("F-1", Pathogen.BKD, "0.05"))
    with pytest.raises(DuplicateError):
        sheet.record(Assay.from_density("f 1", Pathogen.BKD, "0.30"))


def test_a_fish_can_be_filed_once_for_each_pathogen():
    sheet = screen(pathogens=(Pathogen.BKD, Pathogen.IHNV))
    sheet.record(Assay.from_density("F-1", Pathogen.BKD, "0.05"))
    sheet.record(Assay.from_density("F-1", Pathogen.IHNV, "0.05"))
    assert sheet.females_tested() == 1
    assert len(sheet.assays) == 2


def fill(sheet, densities, pathogen=Pathogen.BKD):
    for index, density in enumerate(densities):
        sheet.record(Assay.from_density(f"F-{index:03d}", pathogen, density))
    return sheet


def test_a_screen_is_not_complete_until_every_female_is_in():
    sheet = fill(screen(females=4), ["0.05", "0.05"])
    assert not sheet.is_complete()
    fill(screen(females=2), ["0.05", "0.05"]).is_complete()


def test_a_screen_of_a_take_with_no_females_is_never_complete():
    assert not screen(females=0).is_complete()


def test_a_pending_result_holds_the_screen_open():
    sheet = screen(females=2)
    sheet.record(Assay.from_density("F-1", Pathogen.BKD, "0.05"))
    sheet.record(Assay(tag="F-2", pathogen=Pathogen.BKD, level=AssayLevel.PENDING))
    assert not sheet.is_complete()


def test_the_worst_and_the_prevalence_are_different_questions():
    sheet = fill(screen(females=4), ["0.05", "0.05", "0.05", "0.90"])
    assert sheet.worst(Pathogen.BKD) is AssayLevel.HIGH
    assert sheet.prevalence(Pathogen.BKD) == Decimal("0.25")


def test_a_pathogen_with_no_results_is_pending_and_absent():
    sheet = screen()
    assert sheet.worst(Pathogen.BKD) is AssayLevel.PENDING
    assert sheet.prevalence(Pathogen.BKD) == Decimal(0)


def test_an_incomplete_screen_waits_whatever_the_partial_results_say():
    sheet = fill(screen(females=4), ["0.90"])
    assert disposition(sheet) is Disposition.WAIT


def test_a_clean_screen_releases():
    sheet = fill(screen(females=4), ["0.05", "0.05", "0.05", "0.05"])
    assert disposition(sheet) is Disposition.RELEASE


def test_one_bad_female_in_a_big_take_is_a_segregation():
    sheet = fill(screen(females=4), ["0.05", "0.05", "0.05", "0.90"])
    assert disposition(sheet) is Disposition.SEGREGATE


def test_half_the_take_at_moderate_destroys_it_even_with_no_high_fish():
    sheet = fill(screen(females=4), ["0.25", "0.25", "0.05", "0.05"])
    assert disposition(sheet) is Disposition.DESTROY


def test_a_high_fish_at_prevalence_destroys():
    sheet = fill(screen(females=4), ["0.90", "0.90", "0.05", "0.05"])
    assert disposition(sheet) is Disposition.DESTROY


def test_low_readings_across_the_take_are_not_a_segregation_on_their_own():
    sheet = fill(screen(females=4), ["0.12", "0.12", "0.12", "0.12"])
    assert disposition(sheet) is Disposition.RELEASE


def test_a_pathogen_that_does_not_ride_the_egg_does_not_hold_the_eggs():
    sheet = fill(
        screen(pathogens=(Pathogen.WHIRLING,), females=2), ["0.90", "0.90"], Pathogen.WHIRLING
    )
    assert disposition(sheet) is Disposition.RELEASE


def test_the_station_can_move_where_segregation_starts():
    sheet = fill(screen(females=4), ["0.12", "0.05", "0.05", "0.05"])
    assert disposition(sheet) is Disposition.RELEASE
    assert disposition(sheet, segregate_at=AssayLevel.LOW) is Disposition.SEGREGATE


def test_an_impossible_destroy_prevalence_is_refused():
    sheet = fill(screen(females=4), ["0.05", "0.05", "0.05", "0.05"])
    with pytest.raises(ValidationError):
        disposition(sheet, destroy_prevalence="1.5")


def test_the_worst_pathogen_of_several_drives_the_answer():
    sheet = screen(pathogens=(Pathogen.BKD, Pathogen.IHNV), females=4)
    fill(sheet, ["0.05", "0.05", "0.05", "0.05"], Pathogen.BKD)
    fill(sheet, ["0.90", "0.05", "0.05", "0.05"], Pathogen.IHNV)
    assert disposition(sheet) is Disposition.SEGREGATE
