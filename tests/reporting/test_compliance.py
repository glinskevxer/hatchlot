from datetime import date
from decimal import Decimal

import pytest

from hatchlot.calendar import DateRange
from hatchlot.errors import ValidationError
from hatchlot.health.case import open_case
from hatchlot.health.exam import Examination
from hatchlot.health.exam import Finding as HealthFinding
from hatchlot.marking.mark import MarkPlan, MarkType, TagCode
from hatchlot.marking.run import MarkingRun, QualityCheck
from hatchlot.permits.limits import Basis, Limit, Parameter, Sample
from hatchlot.permits.monitoring import MonitoringRecord, Reading
from hatchlot.permits.permit import Permit, build_report
from hatchlot.quantities.base import Quantity
from hatchlot.reporting.compliance import (
    Area,
    ComplianceReport,
    Finding,
    build_compliance_report,
    render_compliance,
)

MARCH = DateRange("2025-03-01", "2025-03-31")
LOT = "2024-CHK-01"


def permit_report(clean=True):
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
                    outfall=Decimal(2 if clean else 12),
                    flow=Quantity(1000, "Lpm"),
                ),
                taken_by="kt",
            )
        )
    return build_report(permit, record, MARCH)


def health_case():
    sheet = Examination(
        code="EX-001", lot=LOT, day=date(2025, 3, 1), fish_examined=10, inspector="vet"
    )
    for number in range(1, 11):
        sheet.score(number, HealthFinding.PARASITE, 2 if number <= 5 else 0)
    return open_case("HC-001", sheet, HealthFinding.PARASITE, "vet")


def marking_run(accepted=True):
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
        presented=Decimal(10000),
        crew="trailer 3",
    )
    run.start()
    run.finish(Decimal(9900 if accepted else 5000))
    run.check(
        QualityCheck(
            day=date(2025, 3, 5),
            sampled=200,
            marked=198 if accepted else 100,
            tags_detected=190 if accepted else 90,
        )
    )
    run.accept()
    return run


def test_a_finding_needs_a_real_area_and_words():
    with pytest.raises(ValidationError):
        Finding(area="discharge", subject="x", detail="y")  # type: ignore[arg-type]
    with pytest.raises(ValidationError):
        Finding(area=Area.MARKING, subject="  ", detail="y")
    assert "[marking]" in Finding(area=Area.MARKING, subject="x", detail="y").line


def test_the_two_areas_an_outside_body_writes_about():
    assert Area.DISCHARGE.is_regulatory
    assert Area.WITHDRAWAL.is_regulatory
    assert not Area.MARKING.is_regulatory


def test_a_station_with_nothing_wrong_reports_nothing():
    report = build_compliance_report(MARCH, discharge=[permit_report()], runs=[marking_run()])
    assert report.is_clean
    assert report.checked == 2
    assert report.clean_share == Decimal(1)
    assert "nothing outstanding" in report.line()


def test_an_exceeded_permit_becomes_a_discharge_finding():
    report = build_compliance_report(MARCH, discharge=[permit_report(clean=False)])
    assert len(report.for_area(Area.DISCHARGE)) == 1
    assert not report.is_clean


def test_an_open_health_case_becomes_a_finding():
    report = build_compliance_report(MARCH, cases=[health_case()])
    findings = report.for_area(Area.FISH_HEALTH)
    assert len(findings) == 1
    assert LOT in findings[0].subject


def test_a_closed_case_is_not_a_finding():
    case = health_case()
    sheet = Examination(
        code="EX-002", lot=LOT, day=date(2025, 3, 20), fish_examined=10, inspector="vet"
    )
    for number in range(1, 11):
        sheet.score(number, HealthFinding.PARASITE, 0)
    case.close_on("2025-03-20", sheet, "vet")
    assert build_compliance_report(MARCH, cases=[case]).is_clean


def test_a_rejected_marking_run_becomes_a_finding():
    report = build_compliance_report(MARCH, runs=[marking_run(accepted=False)])
    findings = report.for_area(Area.MARKING)
    assert len(findings) == 1
    assert "rejected" in findings[0].detail


def test_a_run_that_was_never_accepted_becomes_a_different_finding():
    plan = MarkPlan(lot=LOT, marks=(MarkType.ADIPOSE_CLIP,))
    unfinished = MarkingRun(
        code="MR-002",
        lot=LOT,
        day=date(2025, 3, 1),
        plan=plan,
        presented=Decimal(1000),
        crew="trailer 3",
    )
    report = build_compliance_report(MARCH, runs=[unfinished])
    assert "not accepted" in report.for_area(Area.MARKING)[0].detail


def test_an_outstanding_withdrawal_becomes_a_finding():
    report = build_compliance_report(
        MARCH, withdrawals={LOT: Decimal(120), "2024-CHK-02": Decimal(0)}
    )
    findings = report.for_area(Area.WITHDRAWAL)
    assert len(findings) == 1
    assert "120" in findings[0].detail


def test_the_regulatory_findings_are_the_ones_somebody_writes_about():
    report = build_compliance_report(
        MARCH,
        discharge=[permit_report(clean=False)],
        runs=[marking_run(accepted=False)],
    )
    assert len(report.findings) == 2
    assert len(report.regulatory) == 1


def test_the_clean_share_of_what_was_checked():
    report = build_compliance_report(
        MARCH, discharge=[permit_report()], runs=[marking_run(accepted=False)]
    )
    assert report.clean_share == Decimal("0.5")
    assert ComplianceReport(window=MARCH, findings=(), checked=0).clean_share == Decimal(0)


def test_the_rendered_report_shows_the_findings_and_the_regulatory_block():
    report = build_compliance_report(MARCH, discharge=[permit_report(clean=False)])
    text = render_compliance(report)
    assert "Compliance" in text
    assert "discharge" in text
    assert "Regulatory" in text


def test_a_clean_report_prints_just_its_heading_and_line():
    text = render_compliance(build_compliance_report(MARCH, runs=[marking_run()]))
    assert "nothing outstanding" in text
    assert "Regulatory" not in text
