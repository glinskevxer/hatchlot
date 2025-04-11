from datetime import date
from decimal import Decimal

import pytest

from hatchlot.calendar import DateRange
from hatchlot.errors import ValidationError
from hatchlot.permits.limits import Basis, Limit, Parameter, Sample
from hatchlot.permits.monitoring import MonitoringRecord, Reading
from hatchlot.permits.permit import Permit, build_report, periods
from hatchlot.quantities.base import Quantity

TERM = DateRange("2025-01-01", "2029-12-31")
MARCH = DateRange("2025-03-01", "2025-03-31")


def limit(value="5", basis=Basis.CONCENTRATION, parameter=Parameter.SUSPENDED_SOLIDS):
    return Limit(parameter=parameter, basis=basis, value=Decimal(value))


def permit(outfalls=("OF-1",), term=TERM, per_month=4):
    entry = Permit(
        code="NPDES-001",
        holder="Cold Creek Hatchery",
        term=term,
        outfalls=outfalls,
        sampling_per_month=per_month,
    )
    entry.add_limit(limit())
    return entry


def reading(day, outfall_value="4", parameter=Parameter.SUSPENDED_SOLIDS):
    return Reading(
        day=date.fromisoformat(day),
        outfall="OF-1",
        sample=Sample(
            parameter=parameter,
            intake=Decimal(0),
            outfall=Decimal(outfall_value),
            flow=Quantity(1000, "Lpm"),
        ),
        taken_by="kt",
    )


def record(*readings):
    book = MonitoringRecord()
    for entry in readings:
        book.record(entry)
    return book


def weekly(values):
    return record(*[reading(f"2025-03-{day:02d}", value) for day, value in values])


def test_a_permit_normalises_its_outfalls_and_needs_a_holder():
    entry = permit(outfalls=(" of 1 ", "OF-2"))
    assert entry.outfalls == ("OF-1", "OF-2")
    with pytest.raises(ValidationError):
        Permit(code="P-1", holder="  ", term=TERM, outfalls=("OF-1",))


def test_a_permit_with_no_outfalls_or_a_repeated_one_is_refused():
    with pytest.raises(ValidationError):
        Permit(code="P-1", holder="X", term=TERM, outfalls=())
    with pytest.raises(ValidationError):
        Permit(code="P-1", holder="X", term=TERM, outfalls=("OF-1", "of 1"))


def test_an_impossible_sampling_frequency_is_refused():
    with pytest.raises(ValidationError):
        permit(per_month=0)


def test_a_limit_goes_on_once_per_parameter_and_basis():
    entry = permit()
    entry.add_limit(limit(basis=Basis.MASS_PER_DAY))
    with pytest.raises(ValidationError):
        entry.add_limit(limit(value="9"))
    assert len(entry.limits_for(Parameter.SUSPENDED_SOLIDS)) == 2


def test_the_permit_knows_its_term_and_its_outfalls():
    entry = permit()
    assert entry.is_in_force("2025-06-01")
    assert not entry.is_in_force("2030-06-01")
    assert entry.covers("of 1")
    assert not entry.covers("OF-9")
    assert entry.expires_in("2029-12-01") == 30
    assert entry.expires_in("2030-01-31") < 0


def test_the_parameters_a_permit_covers():
    entry = permit()
    entry.add_limit(limit(parameter=Parameter.BOD))
    assert set(entry.parameters()) == {Parameter.SUSPENDED_SOLIDS, Parameter.BOD}


def test_a_clean_month_reports_compliant():
    report = build_report(permit(), weekly([(1, "4"), (8, "4"), (15, "4"), (22, "4")]), MARCH)
    assert report.is_compliant
    assert report.failing == ()
    assert report.results[0].samples == 4
    assert report.results[0].average == Decimal(4)
    assert "compliant" in report.line()


def test_a_month_with_a_single_bad_sample_fails():
    report = build_report(permit(), weekly([(1, "12"), (8, "1"), (15, "1"), (22, "1")]), MARCH)
    assert not report.is_compliant
    assert len(report.failing) == 1
    assert report.results[0].maximum == Decimal(12)


def test_a_month_whose_average_is_over_fails_even_with_no_single_exceedance():
    report = build_report(permit(), weekly([(1, "5"), (8, "5"), (15, "5"), (22, "5")]), MARCH)
    assert report.results[0].average == Decimal(5)
    assert report.is_compliant
    over = build_report(permit(), weekly([(1, "5"), (8, "5"), (15, "5"), (22, "4")]), MARCH)
    assert over.is_compliant


def test_a_month_that_missed_its_sampling_is_not_compliant():
    report = build_report(permit(), weekly([(1, "4")]), MARCH)
    assert not report.frequency_met
    assert not report.is_compliant


def test_a_report_outside_the_permit_term_is_not_compliant():
    lapsed = permit(term=DateRange("2020-01-01", "2024-12-31"))
    report = build_report(lapsed, weekly([(1, "4"), (8, "4"), (15, "4"), (22, "4")]), MARCH)
    assert not report.in_force
    assert not report.is_compliant


def test_a_permit_with_no_limits_cannot_be_reported_on():
    entry = Permit(code="P-1", holder="X", term=TERM, outfalls=("OF-1",))
    with pytest.raises(ValidationError):
        build_report(entry, MonitoringRecord(), MARCH)


def test_a_month_with_no_samples_reports_nothing_rather_than_zero():
    report = build_report(permit(), MonitoringRecord(), MARCH)
    assert report.results[0].samples == 0
    assert report.results[0].average is None
    assert report.results[0].maximum is None
    assert report.results[0].worst_share == Decimal(0)
    assert not report.is_compliant


def test_the_worst_share_of_a_limit_result():
    report = build_report(permit(), weekly([(1, "10"), (8, "1"), (15, "1"), (22, "1")]), MARCH)
    assert report.results[0].worst_share == Decimal(2)


def test_a_term_splits_into_reporting_periods():
    quarters = periods(DateRange("2025-01-01", "2025-12-31"), months=3)
    assert len(quarters) == 4
    assert quarters[0].start == date(2025, 1, 1)
    assert quarters[-1].end == date(2025, 12, 31)


def test_monthly_periods_cover_the_whole_term():
    months = periods(DateRange("2025-01-01", "2025-06-30"))
    assert len(months) == 6
    assert months[0].end == date(2025, 2, 1)


def test_a_period_of_no_months_is_refused():
    with pytest.raises(ValidationError):
        periods(TERM, months=0)
