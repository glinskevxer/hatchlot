from datetime import date
from decimal import Decimal

import pytest

from hatchlot.errors import ValidationError
from hatchlot.health.exam import (
    Examination,
    Finding,
    Observation,
    Severity,
    is_sample_adequate,
    worst_of,
)

LOT = "2024-CHK-01"


def exam(code="EX-001", fish=30, lot=LOT):
    return Examination(
        code=code, lot=lot, day=date(2025, 4, 1), fish_examined=fish, inspector="vet"
    )


def test_an_examination_normalises_its_codes_and_needs_an_inspector():
    sheet = exam(code=" ex 001 ")
    assert sheet.code == "EX-001"
    assert sheet.lot == LOT
    with pytest.raises(ValidationError):
        Examination(code="EX-1", lot=LOT, day=date(2025, 4, 1), fish_examined=30, inspector=" ")


def test_an_examination_of_no_fish_is_refused():
    with pytest.raises(ValidationError):
        exam(fish=0)


def test_the_severity_scale_reads_off_a_score():
    assert Severity.from_score(0) is Severity.NONE
    assert Severity.from_score(3) is Severity.SEVERE
    assert not Severity.NONE.is_present
    assert Severity.SLIGHT.is_present


@pytest.mark.parametrize("bad", [-1, 4, "1.5", "x"])
def test_a_score_off_the_scale_is_refused(bad):
    with pytest.raises(ValidationError):
        Severity.from_score(bad)


def test_an_observation_needs_a_real_fish_finding_and_severity():
    with pytest.raises(ValidationError):
        Observation(fish=0, finding=Finding.GILL, severity=Severity.SLIGHT)
    with pytest.raises(ValidationError):
        Observation(fish=1, finding="gill", severity=Severity.SLIGHT)  # type: ignore[arg-type]
    with pytest.raises(ValidationError):
        Observation(fish=1, finding=Finding.GILL, severity=1)  # type: ignore[arg-type]


def test_a_fish_outside_the_sample_is_refused():
    sheet = exam(fish=10)
    with pytest.raises(ValidationError):
        sheet.score(11, Finding.GILL, 1)


def test_a_fish_gets_one_score_per_finding():
    sheet = exam()
    sheet.score(1, Finding.GILL, 1)
    sheet.score(1, Finding.FIN, 2)
    with pytest.raises(ValidationError):
        sheet.score(1, Finding.GILL, 2)


def test_prevalence_counts_the_fish_that_had_it():
    sheet = exam(fish=10)
    for fish in range(1, 6):
        sheet.score(fish, Finding.GILL, 1)
    for fish in range(6, 11):
        sheet.score(fish, Finding.GILL, 0)
    assert sheet.prevalence(Finding.GILL) == Decimal("0.5")
    assert sheet.prevalence(Finding.LESION) == Decimal(0)


def test_the_mean_severity_is_over_the_affected_fish_not_the_sample():
    sheet = exam(fish=10)
    sheet.score(1, Finding.GILL, 3)
    sheet.score(2, Finding.GILL, 1)
    for fish in range(3, 11):
        sheet.score(fish, Finding.GILL, 0)
    assert sheet.mean_severity(Finding.GILL) == Decimal(2)
    assert sheet.mean_severity(Finding.FIN) == Decimal(0)


def test_the_worst_score_for_a_finding():
    sheet = exam()
    sheet.score(1, Finding.LESION, 1)
    sheet.score(2, Finding.LESION, 3)
    assert sheet.worst(Finding.LESION) is Severity.SEVERE
    assert sheet.worst(Finding.EYE) is Severity.NONE


def test_a_clean_examination_finds_nothing():
    sheet = exam()
    sheet.score(1, Finding.GILL, 0)
    assert sheet.is_clean()
    assert sheet.findings_present() == ()


def test_the_findings_that_were_present():
    sheet = exam()
    sheet.score(1, Finding.GILL, 1)
    sheet.score(2, Finding.BEHAVIOUR, 2)
    assert set(sheet.findings_present()) == {Finding.GILL, Finding.BEHAVIOUR}
    assert not sheet.is_clean()


def test_behaviour_is_the_one_finding_that_is_not_external():
    assert Finding.GILL.is_external
    assert not Finding.BEHAVIOUR.is_external


def test_a_sample_big_enough_to_say_anything():
    assert is_sample_adequate(exam(fish=30), 50000)
    assert not is_sample_adequate(exam(fish=10), 50000)
    assert is_sample_adequate(exam(fish=10), 50000, minimum=5)


def test_a_sample_of_the_whole_lot_is_always_adequate():
    assert is_sample_adequate(exam(fish=10), 10)
    assert is_sample_adequate(exam(fish=10), 5)


def test_a_sample_against_no_population_is_refused():
    with pytest.raises(ValidationError):
        is_sample_adequate(exam(), 0)


def test_the_worst_examination_of_several():
    light = exam(code="EX-001", fish=10)
    light.score(1, Finding.GILL, 1)
    heavy = exam(code="EX-002", fish=10)
    for fish in range(1, 6):
        heavy.score(fish, Finding.GILL, 2)
    assert worst_of([light, heavy], Finding.GILL) is heavy
    assert worst_of([], Finding.GILL) is None
