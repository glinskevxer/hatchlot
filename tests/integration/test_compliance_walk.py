"""A month of compliance, walked the way an audit would walk it.

The point of this one is the interaction between the holds. A lot can be clear
on its permit, clear on its marking and still not releasable because a drug
withdrawal has not run out, and the only place that shows up is when all four
registers are read together.
"""

from datetime import date, timedelta
from decimal import Decimal

import pytest

from hatchlot.calendar import DateRange
from hatchlot.distribution.haul import HaulLoad, OxygenSupply, Tank
from hatchlot.distribution.release import ReleaseKind, release_fish
from hatchlot.distribution.request import StockingRequest
from hatchlot.errors import PolicyError
from hatchlot.feed.medicated import Drug, Prescription, withdrawal_for
from hatchlot.health.case import open_case
from hatchlot.health.exam import Examination, Finding
from hatchlot.health.treatment import Chemical, Method, Treatment
from hatchlot.marking.mark import MarkPlan, MarkType, TagCode
from hatchlot.marking.run import MarkingRun, QualityCheck, RunState
from hatchlot.permits.limits import Basis, Limit, Parameter, Sample
from hatchlot.permits.monitoring import MonitoringRecord, Reading
from hatchlot.permits.permit import Permit, build_report
from hatchlot.quantities.base import Quantity
from hatchlot.quantities.temperature import Temperature
from hatchlot.reporting.compliance import Area, build_compliance_report
from hatchlot.water.thermal import ThermalSeries

MARCH = DateRange("2025-03-01", "2025-03-31")
LOT = "2024-CHK-01"


def water(start=date(2025, 3, 1), days=200, celsius="10"):
    series = ThermalSeries()
    for offset in range(days):
        series.add(start + timedelta(days=offset), celsius)
    return series


def permit_with_readings(outfall_value="2"):
    permit = Permit(
        code="NPDES-001",
        holder="Cold Creek",
        term=DateRange("2025-01-01", "2029-12-31"),
        outfalls=("OF-1",),
    )
    permit.add_limit(
        Limit(parameter=Parameter.SUSPENDED_SOLIDS, basis=Basis.CONCENTRATION, value=Decimal(5))
    )
    record = MonitoringRecord()
    for day in (1, 8, 15, 22):
        record.record(
            Reading(
                day=date(2025, 3, day),
                outfall="OF-1",
                sample=Sample(
                    parameter=Parameter.SUSPENDED_SOLIDS,
                    intake=Decimal(0),
                    outfall=Decimal(outfall_value),
                    flow=Quantity(1000, "Lpm"),
                ),
                taken_by="kt",
            )
        )
    return build_report(permit, record, MARCH)


def accepted_run():
    plan = MarkPlan(
        lot=LOT,
        marks=(MarkType.ADIPOSE_CLIP, MarkType.CODED_WIRE_TAG),
        tag_code=TagCode("05-12-34"),
    )
    run = MarkingRun(
        code="MR-001",
        lot=LOT,
        day=date(2025, 3, 1),
        plan=plan,
        presented=Decimal(20000),
        crew="trailer 3",
    )
    run.start()
    run.finish(Decimal(19800))
    run.check(QualityCheck(day=date(2025, 3, 10), sampled=200, marked=199, tags_detected=195))
    run.accept()
    return run


def parasite_case():
    sheet = Examination(
        code="EX-001", lot=LOT, day=date(2025, 3, 2), fish_examined=10, inspector="vet"
    )
    for number in range(1, 11):
        sheet.score(number, Finding.PARASITE, 2 if number <= 5 else 0)
    return open_case("HC-001", sheet, Finding.PARASITE, "vet")


def prescription():
    return Prescription(
        code="RX-001",
        lot=LOT,
        drug=Drug.OXYTETRACYCLINE,
        dose_mg_per_kg=Decimal(75),
        days=10,
        start=date(2025, 3, 5),
        prescribed_by="vet",
    )


def test_a_clean_month_has_nothing_outstanding():
    report = build_compliance_report(
        MARCH, discharge=[permit_with_readings()], runs=[accepted_run()]
    )
    assert report.is_clean
    assert report.clean_share == Decimal(1)


def test_a_treated_lot_is_open_on_three_of_the_four_areas():
    case = parasite_case()
    case.treat(
        "2025-03-05",
        Treatment(
            lot=LOT,
            chemical=Chemical.FORMALIN,
            method=Method.FLUSH,
            concentration_ppm=Decimal(167),
            minutes=Decimal(60),
            water=Temperature(10, "C"),
            flow=Quantity(500, "gpm"),
        ),
        "kt",
    )
    hold = withdrawal_for(prescription())
    report = build_compliance_report(
        MARCH,
        discharge=[permit_with_readings(outfall_value="12")],
        cases=[case],
        runs=[accepted_run()],
        withdrawals={LOT: hold.remaining(water(), "2025-03-20")},
    )
    assert len(report.for_area(Area.DISCHARGE)) == 1
    assert len(report.for_area(Area.FISH_HEALTH)) == 1
    assert len(report.for_area(Area.WITHDRAWAL)) == 1
    assert report.for_area(Area.MARKING) == ()


def test_the_withdrawal_clears_on_the_water_and_the_finding_goes_away():
    hold = withdrawal_for(prescription())
    series = water()
    assert not hold.is_clear(series, "2025-03-20")
    assert hold.is_clear(series, "2025-06-01")
    report = build_compliance_report(MARCH, withdrawals={LOT: hold.remaining(series, "2025-06-01")})
    assert report.is_clean


def test_a_release_is_refused_while_the_withdrawal_stands():
    request = StockingRequest(
        code="SR-001",
        water="LAKE-A",
        species="CHK",
        fish=Decimal(20000),
        target_weight=Quantity(20, "g"),
        window=DateRange("2025-03-01", "2025-05-31"),
        requested_by="biologist",
    )
    haul = HaulLoad(
        code="HL-001",
        tanks=[Tank(code="TK-1", volume=Quantity(6000, "L"), supply=OxygenSupply.BOTTLED)],
        fish=Decimal(15000),
        mean_weight=Quantity(20, "g"),
        hours=Decimal(3),
        load_water=Temperature(10, "C"),
        driver="jt",
    )
    hold = withdrawal_for(prescription())
    clear = hold.is_clear(water(), "2025-03-20")
    with pytest.raises(PolicyError) as excinfo:
        release_fish(
            request,
            haul,
            code="RL-001",
            day="2025-03-20",
            lot=LOT,
            kind=ReleaseKind.DIRECT,
            released_by="kt",
            receiving_water=Temperature(11, "C"),
            withdrawal_clear=clear,
        )
    assert excinfo.value.rule == "release.withdrawal"
    assert request.delivered == Decimal(0)


def test_the_same_release_goes_through_once_the_hold_has_cleared():
    request = StockingRequest(
        code="SR-001",
        water="LAKE-A",
        species="CHK",
        fish=Decimal(20000),
        target_weight=Quantity(20, "g"),
        window=DateRange("2025-03-01", "2025-06-30"),
        requested_by="biologist",
    )
    haul = HaulLoad(
        code="HL-001",
        tanks=[Tank(code="TK-1", volume=Quantity(6000, "L"), supply=OxygenSupply.BOTTLED)],
        fish=Decimal(15000),
        mean_weight=Quantity(20, "g"),
        hours=Decimal(3),
        load_water=Temperature(10, "C"),
        driver="jt",
    )
    hold = withdrawal_for(prescription())
    release = release_fish(
        request,
        haul,
        code="RL-001",
        day="2025-06-01",
        lot=LOT,
        kind=ReleaseKind.DIRECT,
        released_by="kt",
        receiving_water=Temperature(11, "C"),
        withdrawal_clear=hold.is_clear(water(), "2025-06-01"),
    )
    assert release.fish == Decimal(15000)
    assert request.delivered == Decimal(15000)


def test_a_rejected_marking_run_holds_the_release_on_its_own():
    plan = MarkPlan(lot=LOT, marks=(MarkType.ADIPOSE_CLIP,))
    run = MarkingRun(
        code="MR-002",
        lot=LOT,
        day=date(2025, 3, 1),
        plan=plan,
        presented=Decimal(20000),
        crew="trailer 3",
    )
    run.start()
    run.finish(Decimal(10000))
    run.check(QualityCheck(day=date(2025, 3, 10), sampled=200, marked=100))
    assert run.accept() is RunState.REJECTED
    report = build_compliance_report(MARCH, runs=[run])
    assert len(report.for_area(Area.MARKING)) == 1
    assert not report.is_clean
