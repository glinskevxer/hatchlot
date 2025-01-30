from datetime import date
from decimal import Decimal

import pytest

from hatchlot.calendar import DateRange
from hatchlot.errors import ValidationError
from hatchlot.health import Finding, open_case, summarise_health
from hatchlot.health.exam import Examination
from hatchlot.health.summary import is_outbreak, stale_cases, treatment_load
from hatchlot.health.treatment import Chemical, Method, Treatment
from hatchlot.quantities.base import Quantity
from hatchlot.quantities.temperature import Temperature

APRIL = DateRange("2025-04-01", "2025-04-30")


def exam(lot="2024-CHK-01", day="2025-04-01", affected=5, finding=Finding.PARASITE):
    sheet = Examination(
        code=f"EX-{lot[-2:]}",
        lot=lot,
        day=date.fromisoformat(day),
        fish_examined=10,
        inspector="vet",
    )
    for number in range(1, 11):
        sheet.score(number, finding, 2 if number <= affected else 0)
    return sheet


def case(code="HC-001", lot="2024-CHK-01", day="2025-04-01", finding=Finding.PARASITE):
    return open_case(code, exam(lot=lot, day=day, finding=finding), finding, "vet")


def treatment():
    return Treatment(
        lot="2024-CHK-01",
        chemical=Chemical.FORMALIN,
        method=Method.STATIC,
        concentration_ppm=Decimal(167),
        minutes=Decimal(60),
        water=Temperature(10, "C"),
        volume=Quantity(90, "m3"),
    )


def test_a_station_with_nothing_open_reads_quiet():
    summary = summarise_health([], [], APRIL, "2025-04-30")
    assert summary.open_cases == ()
    assert summary.held_lots == ()
    assert summary.common_finding is None
    assert summary.oldest_open_days == 0
    assert not summary.looks_like_one_problem


def test_the_examinations_inside_the_window_are_counted():
    summary = summarise_health([], [exam(), exam(day="2025-05-05")], APRIL, "2025-04-30")
    assert summary.examinations == 1


def test_an_open_case_holds_its_lot():
    summary = summarise_health([case()], [exam()], APRIL, "2025-04-30")
    assert summary.open_cases == ("HC-001",)
    assert summary.held_lots == ("2024-CHK-01",)
    assert summary.cases_opened == 1
    assert summary.oldest_open_days == 29


def test_a_closed_case_stops_holding_and_counts_toward_the_resolved_share():
    entry = case()
    entry.close_on("2025-04-20", exam(day="2025-04-20", affected=0), "vet")
    summary = summarise_health([entry], [], APRIL, "2025-04-30")
    assert summary.open_cases == ()
    assert summary.held_lots == ()
    assert summary.cases_closed == 1
    assert summary.resolved_share == Decimal(1)


def test_a_case_that_persisted_pulls_the_resolved_share_down():
    resolved = case(code="HC-001")
    resolved.close_on("2025-04-20", exam(day="2025-04-20", affected=0), "vet")
    persisted = case(code="HC-002", lot="2024-CHK-02")
    persisted.close_on("2025-04-20", exam(lot="2024-CHK-02", day="2025-04-20", affected=5), "vet")
    summary = summarise_health([resolved, persisted], [], APRIL, "2025-04-30")
    assert summary.resolved_share == Decimal("0.5")


def test_the_most_common_open_finding():
    cases = [
        case(code="HC-001", lot="2024-CHK-01"),
        case(code="HC-002", lot="2024-CHK-02"),
        case(code="HC-003", lot="2024-CHK-03", finding=Finding.GILL),
    ]
    summary = summarise_health(cases, [], APRIL, "2025-04-30")
    assert summary.common_finding is Finding.PARASITE
    assert "parasite" in summary.line()


def test_three_lots_with_the_same_finding_looks_like_one_problem():
    cases = [case(code=f"HC-00{n}", lot=f"2024-CHK-0{n}") for n in (1, 2, 3)]
    summary = summarise_health(cases, [], APRIL, "2025-04-30")
    assert summary.looks_like_one_problem


def test_two_lots_are_not_enough_to_call_it_one_problem():
    cases = [case(code=f"HC-00{n}", lot=f"2024-CHK-0{n}") for n in (1, 2)]
    assert not summarise_health(cases, [], APRIL, "2025-04-30").looks_like_one_problem


def test_the_cases_that_have_been_open_too_long():
    old = case(code="HC-001", day="2025-04-01")
    fresh = case(code="HC-002", lot="2024-CHK-02", day="2025-04-25")
    assert [entry.code for entry in stale_cases([old, fresh], "2025-05-05")] == ["HC-001"]
    assert stale_cases([old, fresh], "2025-05-05", days=60) == ()
    with pytest.raises(ValidationError):
        stale_cases([old], "2025-05-05", days=0)


def test_how_many_treatments_the_station_has_given():
    entry = case()
    entry.treat("2025-04-02", treatment(), "kt")
    entry.treat("2025-04-05", treatment(), "kt")
    assert treatment_load([entry, case(code="HC-002", lot="2024-CHK-02")]) == 2


def test_an_outbreak_needs_enough_lots_and_enough_of_the_open_cases():
    cases = [case(code=f"HC-00{n}", lot=f"2024-CHK-0{n}") for n in (1, 2, 3)]
    assert is_outbreak(cases, Finding.PARASITE)
    assert not is_outbreak(cases, Finding.GILL)
    assert not is_outbreak(cases[:2], Finding.PARASITE)


def test_a_scattering_of_findings_is_not_an_outbreak():
    cases = [
        case(code="HC-001", lot="2024-CHK-01"),
        case(code="HC-002", lot="2024-CHK-02"),
        case(code="HC-003", lot="2024-CHK-03", finding=Finding.GILL),
        case(code="HC-004", lot="2024-CHK-04", finding=Finding.FIN),
        case(code="HC-005", lot="2024-CHK-05", finding=Finding.EYE),
    ]
    assert not is_outbreak(cases, Finding.PARASITE)


def test_an_impossible_outbreak_share_is_refused():
    cases = [case(code=f"HC-00{n}", lot=f"2024-CHK-0{n}") for n in (1, 2, 3)]
    with pytest.raises(ValidationError):
        is_outbreak(cases, Finding.PARASITE, share=0)
