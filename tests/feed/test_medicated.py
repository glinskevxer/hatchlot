from datetime import date
from decimal import Decimal

import pytest

from hatchlot.errors import PolicyError, ValidationError
from hatchlot.feed.medicated import (
    Drug,
    Prescription,
    dose_delivered,
    inclusion_rate,
    is_course_complete,
    medicated_feed_needed,
    withdrawal_for,
)
from hatchlot.numeric import quantize
from hatchlot.quantities.base import Quantity
from hatchlot.water.thermal import ThermalSeries

LOT = "2024-CHK-01"


def steady(start="2025-03-01", days=200, celsius="10"):
    series = ThermalSeries()
    first = date.fromisoformat(start)
    for offset in range(days):
        series.add(date.fromordinal(first.toordinal() + offset), celsius)
    return series


def prescription(drug=Drug.OXYTETRACYCLINE, dose="75", days=10, start="2025-03-01"):
    return Prescription(
        code="RX-001",
        lot=LOT,
        drug=drug,
        dose_mg_per_kg=Decimal(dose),
        days=days,
        start=date.fromisoformat(start),
        prescribed_by="vet",
    )


def test_a_prescription_normalises_its_codes_and_keeps_the_prescriber():
    order = prescription()
    assert order.code == "RX-001"
    assert order.lot == LOT
    assert order.prescribed_by == "vet"


def test_a_prescription_needs_a_dose_a_course_and_a_prescriber():
    with pytest.raises(ValidationError):
        prescription(dose="0")
    with pytest.raises(ValidationError):
        prescription(days=0)
    with pytest.raises(ValidationError):
        Prescription(
            code="RX-1",
            lot=LOT,
            drug=Drug.FLORFENICOL,
            dose_mg_per_kg=Decimal(10),
            days=10,
            start=date(2025, 3, 1),
            prescribed_by="  ",
        )


def test_a_drug_that_is_not_a_drug_is_refused():
    with pytest.raises(ValidationError):
        Prescription(
            code="RX-1",
            lot=LOT,
            drug="florfenicol",  # type: ignore[arg-type]
            dose_mg_per_kg=Decimal(10),
            days=10,
            start=date(2025, 3, 1),
            prescribed_by="vet",
        )


def test_the_course_window_covers_the_days_it_runs():
    assert prescription(days=10).window.days == 10
    assert prescription(days=10).window.end == date(2025, 3, 10)


def test_a_course_on_the_label_is_not_off_label():
    assert not prescription().is_off_label
    assert prescription(dose="100").is_off_label
    assert prescription(days=14).is_off_label


def test_the_drug_a_lot_needs_in_a_day_and_over_a_course():
    order = prescription(dose="75", days=10)
    assert order.daily_drug(Quantity(1000, "kg")) == Decimal(75000)
    assert order.total_drug(Quantity(1000, "kg")) == Decimal(750000)
    with pytest.raises(ValidationError):
        order.daily_drug(Quantity(0, "kg"))


def test_the_inclusion_rate_goes_through_the_feeding_rate():
    order = prescription(dose="75")
    assert inclusion_rate(order, 2) == Decimal(3750)
    assert inclusion_rate(order, 1) == Decimal(7500)


def test_an_impossible_feeding_rate_is_refused():
    order = prescription()
    with pytest.raises(ValidationError):
        inclusion_rate(order, 0)
    with pytest.raises(ValidationError):
        inclusion_rate(order, 50)


def test_the_medicated_feed_a_course_takes():
    order = prescription(days=10)
    assert medicated_feed_needed(order, Quantity(1000, "kg"), 2) == Quantity(200, "kg")
    with pytest.raises(ValidationError):
        medicated_feed_needed(order, Quantity(1000, "kg"), 0)


def test_the_withdrawal_is_counted_in_degree_days_off_the_last_dose():
    hold = withdrawal_for(prescription())
    assert hold.last_dose == date(2025, 3, 10)
    assert hold.required_degree_days == Decimal(400)


def test_a_cold_spring_is_a_longer_withdrawal_than_a_warm_one():
    hold = withdrawal_for(prescription())
    warm = steady(start="2025-03-11", celsius="10")
    cold = steady(start="2025-03-11", celsius="5")
    assert hold.is_clear(warm, "2025-04-30")
    assert not hold.is_clear(cold, "2025-04-30")


def test_the_hold_reports_how_much_is_left():
    hold = withdrawal_for(prescription())
    series = steady(start="2025-03-11", celsius="10")
    assert hold.remaining(series, "2025-03-21") == Decimal(290)
    assert hold.remaining(series, "2025-06-01") == Decimal(0)
    assert hold.accumulated(series, "2025-03-01") == Decimal(0)


def test_a_release_inside_the_withdrawal_is_refused_by_name():
    hold = withdrawal_for(prescription())
    series = steady(start="2025-03-11", celsius="10")
    with pytest.raises(PolicyError) as excinfo:
        hold.check(series, "2025-03-21")
    assert excinfo.value.rule == "feed.withdrawal"
    hold.check(series, "2025-06-01")


def test_the_day_the_hold_lifts_and_the_projection_when_the_record_runs_out():
    hold = withdrawal_for(prescription())
    series = steady(start="2025-03-11", days=60, celsius="10")
    assert hold.clears_on(series) == date(2025, 4, 19)
    short = steady(start="2025-03-11", days=5, celsius="10")
    assert hold.clears_on(short) is None
    assert hold.clears_on(short, assumed_celsius=10) == date(2025, 4, 19)


def test_a_last_dose_before_the_course_started_is_refused():
    with pytest.raises(ValidationError):
        withdrawal_for(prescription(), last_dose="2025-02-01")


def test_a_course_cut_short_moves_the_hold_forward():
    hold = withdrawal_for(prescription(), last_dose="2025-03-05")
    assert hold.last_dose == date(2025, 3, 5)


def test_the_dose_the_fish_actually_got_off_the_feeding_record():
    got = dose_delivered(Quantity(200, "kg"), 3750, Quantity(1000, "kg"))
    assert quantize(got, 0) == Decimal(750)


def test_a_course_fed_short_is_not_a_complete_course():
    order = prescription(dose="75", days=10)
    assert is_course_complete(order, 750)
    assert is_course_complete(order, 700)
    assert not is_course_complete(order, 400)


def test_an_impossible_completion_tolerance_is_refused():
    order = prescription()
    with pytest.raises(ValidationError):
        is_course_complete(order, 750, tolerance=0)
    with pytest.raises(ValidationError):
        is_course_complete(order, 750, tolerance="1.5")


def test_every_drug_carries_a_label_and_a_withdrawal():
    for drug in Drug:
        assert drug.withdrawal_degree_days > 0
        assert drug.label_dose_mg_per_kg > 0
        assert drug.label_days > 0
