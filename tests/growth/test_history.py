from datetime import date
from decimal import Decimal

import pytest

from hatchlot.calendar import DateRange
from hatchlot.errors import ValidationError
from hatchlot.growth.history import GrowthHistory, WeighIn, growth_between, refit
from hatchlot.growth.model import GrowthModel
from hatchlot.quantities.base import Quantity
from hatchlot.water.thermal import ThermalSeries

LOT = "2024-CHK-01"
MODEL = GrowthModel(coefficient=Decimal(2))


def steady(start="2025-01-01", days=400, celsius="10"):
    series = ThermalSeries()
    first = date.fromisoformat(start)
    for offset in range(days):
        series.add(date.fromordinal(first.toordinal() + offset), celsius)
    return series


def history(*entries):
    log = GrowthHistory()
    for day, grams in entries:
        log.record(WeighIn(day, LOT, Quantity(str(grams), "g")))
    return log


def test_a_weigh_in_normalises_its_lot_and_needs_a_weight():
    entry = WeighIn("2025-02-01", " 2024 chk 01 ", Quantity(2, "g"))
    assert entry.lot == LOT
    with pytest.raises(ValidationError):
        WeighIn("2025-02-01", LOT, Quantity(0, "g"))


def test_the_latest_weight_and_the_span_of_a_lot():
    log = history(("2025-01-01", 1), ("2025-04-10", 27))
    assert log.latest_weight(LOT) == Quantity(27, "g")
    assert log.span_for(LOT) == DateRange("2025-01-01", "2025-04-10")
    assert log.latest_weight("2024-CHK-09") is None


def test_one_weigh_in_is_not_a_span():
    log = history(("2025-01-01", 1))
    assert log.span_for(LOT) is None
    with pytest.raises(ValidationError):
        log.observed_model(LOT, steady())
    with pytest.raises(ValidationError):
        log.against(LOT, MODEL, steady())


def test_the_coefficient_a_lot_is_really_growing_at():
    log = history(("2025-01-01", 1), ("2025-04-10", 27))
    fitted = log.observed_model(LOT, steady())
    assert fitted.coefficient.quantize(Decimal("0.01")) == Decimal("2.00")


def test_a_lot_on_plan_reads_as_tracking():
    log = history(("2025-01-01", 1), ("2025-04-10", 27))
    assert abs(log.against(LOT, MODEL, steady())) < Decimal(1)
    assert log.is_tracking(LOT, MODEL, steady())


def test_a_lot_behind_the_plan_shows_a_negative_difference():
    log = history(("2025-01-01", 1), ("2025-04-10", 15))
    assert log.against(LOT, MODEL, steady()) < 0
    assert not log.is_tracking(LOT, MODEL, steady())


def test_a_lot_ahead_of_the_plan_shows_a_positive_one():
    log = history(("2025-01-01", 1), ("2025-04-10", 40))
    assert log.against(LOT, MODEL, steady()) > 0


def test_the_tracking_band_can_be_widened():
    log = history(("2025-01-01", 1), ("2025-04-10", 15))
    assert log.is_tracking(LOT, MODEL, steady(), tolerance=90)
    with pytest.raises(ValidationError):
        log.is_tracking(LOT, MODEL, steady(), tolerance=0)


def test_a_lot_that_has_not_grown_in_three_weeks_has_stalled():
    log = history(("2025-01-01", 10), ("2025-02-01", 10), ("2025-02-25", "10.2"))
    assert log.has_stalled(LOT)


def test_a_lot_that_is_growing_has_not_stalled():
    log = history(("2025-01-01", 10), ("2025-02-01", 14), ("2025-02-25", 18))
    assert not log.has_stalled(LOT)


def test_a_lot_with_too_little_history_has_not_stalled():
    assert not history(("2025-01-01", 10)).has_stalled(LOT)
    assert not history(("2025-01-01", 10), ("2025-01-05", 10)).has_stalled(LOT)


def test_the_stall_window_and_the_gain_it_wants_can_both_be_moved():
    log = history(("2025-01-01", 10), ("2025-02-01", 12))
    assert not log.has_stalled(LOT, gain="0.1")
    assert log.has_stalled(LOT, gain="0.5")


def test_the_growth_inside_a_window():
    log = history(("2025-01-01", 10), ("2025-02-01", 14), ("2025-04-01", 30))
    gained = growth_between(log, LOT, DateRange("2025-01-01", "2025-02-28"))
    assert gained == Quantity(4, "g")
    assert growth_between(log, LOT, DateRange("2025-03-01", "2025-03-31")) is None


def test_refitting_hands_back_the_observed_model():
    log = history(("2025-01-01", 1), ("2025-04-10", 27))
    assert refit(log, LOT, steady()).coefficient == log.observed_model(LOT, steady()).coefficient
