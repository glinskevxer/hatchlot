from datetime import date
from decimal import Decimal

import pytest

from hatchlot.errors import PolicyError, StateError, ValidationError
from hatchlot.health.case import Case, CaseState, Outcome, improvement, open_case
from hatchlot.health.exam import Examination, Finding
from hatchlot.health.treatment import Chemical, Method, Treatment
from hatchlot.quantities.base import Quantity
from hatchlot.quantities.temperature import Temperature

LOT = "2024-CHK-01"


def exam(day="2025-04-01", affected=5, fish=10, lot=LOT, finding=Finding.PARASITE):
    sheet = Examination(
        code="EX-001",
        lot=lot,
        day=date.fromisoformat(day),
        fish_examined=fish,
        inspector="vet",
    )
    for number in range(1, fish + 1):
        sheet.score(number, finding, 2 if number <= affected else 0)
    return sheet


def treatment(concentration="167"):
    return Treatment(
        lot=LOT,
        chemical=Chemical.FORMALIN,
        method=Method.STATIC,
        concentration_ppm=Decimal(concentration),
        minutes=Decimal(60),
        water=Temperature(10, "C"),
        volume=Quantity(90, "m3"),
    )


def case():
    return open_case("HC-001", exam(), Finding.PARASITE, "vet")


def test_a_case_opens_off_an_examination_and_takes_the_prevalence():
    entry = case()
    assert entry.code == "HC-001"
    assert entry.lot == LOT
    assert entry.opening_prevalence == Decimal("0.5")
    assert entry.state is CaseState.OPEN
    assert entry.is_open
    assert entry.holds_lot


def test_a_case_cannot_be_opened_on_an_examination_that_found_nothing():
    with pytest.raises(ValidationError):
        open_case("HC-002", exam(affected=0), Finding.PARASITE, "vet")


def test_a_case_needs_a_real_finding_and_whoever_opened_it():
    with pytest.raises(ValidationError):
        Case(
            code="HC-1",
            lot=LOT,
            finding="parasite",  # type: ignore[arg-type]
            opened_on=date(2025, 4, 1),
            opened_by="vet",
        )
    with pytest.raises(ValidationError):
        Case(
            code="HC-1",
            lot=LOT,
            finding=Finding.PARASITE,
            opened_on=date(2025, 4, 1),
            opened_by=" ",
        )


def test_a_diagnosis_goes_on_the_record_with_words_in_it():
    entry = case()
    entry.diagnose("2025-04-02", "ichthyophthirius", "vet")
    assert entry.diagnosis == "ichthyophthirius"
    with pytest.raises(ValidationError):
        entry.diagnose("2025-04-03", "  ", "vet")


def test_a_treatment_moves_the_case_on_without_ending_it():
    entry = case()
    entry.treat("2025-04-02", treatment(), "kt")
    assert entry.state is CaseState.TREATING
    assert entry.is_open
    assert entry.treatments_given() == 1


def test_an_unsafe_treatment_is_refused_before_it_reaches_the_record():
    entry = case()
    with pytest.raises(PolicyError):
        entry.treat("2025-04-02", treatment(concentration="400"), "kt")
    assert entry.treatments_given() == 0


def test_events_cannot_be_written_out_of_order():
    entry = case()
    entry.treat("2025-04-05", treatment(), "kt")
    with pytest.raises(ValidationError):
        entry.watch("2025-04-02", "kt")


def test_watching_and_escalating_both_keep_the_lot_held():
    entry = case()
    entry.watch("2025-04-05", "kt")
    assert entry.state is CaseState.WATCHING
    assert entry.holds_lot
    entry.escalate("2025-04-06", "kt", "not responding")
    assert entry.state.value == "escalated"
    assert entry.holds_lot


def test_an_escalation_needs_a_reason():
    entry = case()
    with pytest.raises(ValidationError):
        entry.escalate("2025-04-05", "kt", " ")


def test_a_case_closes_on_a_clean_follow_up():
    entry = case()
    entry.treat("2025-04-02", treatment(), "kt")
    outcome = entry.close_on("2025-04-20", exam(day="2025-04-20", affected=0), "vet")
    assert outcome is Outcome.RESOLVED
    assert entry.state is CaseState.CLOSED
    assert not entry.holds_lot
    assert not entry.is_open


def test_a_follow_up_that_still_finds_it_closes_as_persisted():
    entry = case()
    outcome = entry.close_on("2025-04-20", exam(day="2025-04-20", affected=4), "vet")
    assert outcome is Outcome.PERSISTED
    assert entry.closing_prevalence == Decimal("0.4")


def test_the_clearance_threshold_can_be_moved():
    entry = case()
    outcome = entry.close_on(
        "2025-04-20", exam(day="2025-04-20", affected=1), "vet", cleared_below="0.2"
    )
    assert outcome is Outcome.RESOLVED


def test_a_follow_up_of_another_lot_or_before_the_case_is_refused():
    entry = case()
    with pytest.raises(ValidationError):
        entry.close_on("2025-04-20", exam(day="2025-04-20", lot="2024-CHK-02"), "vet")
    with pytest.raises(ValidationError):
        entry.close_on("2025-04-20", exam(day="2025-03-01"), "vet")


def test_nothing_happens_on_a_closed_case():
    entry = case()
    entry.close_on("2025-04-20", exam(day="2025-04-20", affected=0), "vet")
    with pytest.raises(StateError):
        entry.treat("2025-04-21", treatment(), "kt")
    with pytest.raises(StateError):
        entry.diagnose("2025-04-21", "something", "vet")
    with pytest.raises(StateError):
        entry.watch("2025-04-21", "kt")
    with pytest.raises(StateError):
        entry.escalate("2025-04-21", "kt", "again")
    with pytest.raises(StateError):
        entry.close_on("2025-04-21", exam(day="2025-04-21", affected=0), "vet")


def test_a_case_can_be_abandoned_only_when_there_is_nothing_left_to_examine():
    entry = case()
    assert entry.abandon("2025-04-20", "vet", Outcome.LOT_LOST) is Outcome.LOT_LOST
    other = case()
    with pytest.raises(ValidationError):
        other.abandon("2025-04-20", "vet", Outcome.RESOLVED)


def test_an_abandoned_case_cannot_be_abandoned_twice():
    entry = case()
    entry.abandon("2025-04-20", "vet", Outcome.NOT_A_CASE)
    with pytest.raises(StateError):
        entry.abandon("2025-04-21", "vet", Outcome.LOT_LOST)


def test_how_long_a_case_has_been_open():
    entry = case()
    assert entry.duration("2025-04-20") == 19
    with pytest.raises(ValidationError):
        entry.duration("2025-03-01")


def test_the_improvement_a_case_shows():
    entry = case()
    entry.close_on("2025-04-20", exam(day="2025-04-20", affected=1), "vet")
    assert improvement(entry) == Decimal("0.8")


def test_an_open_case_has_no_improvement_to_report():
    assert improvement(case()) is None
