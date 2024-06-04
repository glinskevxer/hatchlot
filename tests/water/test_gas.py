from decimal import Decimal

import pytest

from hatchlot.errors import ValidationError
from hatchlot.numeric import quantize
from hatchlot.quantities.base import Quantity
from hatchlot.water.gas import GasReading, GasRisk, blended_delta_p, compensation_depth


def test_a_reading_at_the_barometer_is_a_hundred_percent_and_no_delta():
    reading = GasReading(760, 760)
    assert reading.percent == Decimal(100)
    assert reading.delta_p == Decimal(0)
    assert not reading.is_supersaturated


def test_supersaturation_shows_in_both_the_percent_and_the_delta():
    reading = GasReading(800, 760)
    assert quantize(reading.percent, 1) == Decimal("105.3")
    assert reading.delta_p == Decimal(40)
    assert reading.is_supersaturated


@pytest.mark.parametrize("bad", [0, "-5"])
def test_an_impossible_reading_is_refused(bad):
    with pytest.raises(ValidationError):
        GasReading(bad, 760)
    with pytest.raises(ValidationError):
        GasReading(760, bad)


def test_a_negative_depth_is_refused():
    with pytest.raises(ValidationError):
        GasReading(760, 760, -1)


def test_depth_buys_back_pressure_at_seventy_three_millimetres_a_metre():
    shallow = GasReading(800, 760, 0)
    deep = GasReading(800, 760, "0.5")
    assert shallow.compensated_delta_p == Decimal(40)
    assert quantize(deep.compensated_delta_p, 2) == Decimal("3.29")


def test_a_deep_enough_unit_takes_the_reading_negative():
    assert GasReading(800, 760, 1).compensated_delta_p < 0


def test_the_risk_bands_run_in_the_order_they_get_worse():
    assert GasReading(770, 760).risk() is GasRisk.SAFE
    assert GasReading(790, 760).risk() is GasRisk.WATCH
    assert GasReading(840, 760).risk() is GasRisk.HAZARD


def test_only_the_safe_band_needs_nothing_done():
    assert not GasRisk.SAFE.is_actionable
    assert GasRisk.WATCH.is_actionable
    assert GasRisk.HAZARD.is_actionable


def test_a_deep_raceway_can_hold_a_hazard_reading_down_to_a_watch():
    assert GasReading(840, 760, "0.5").risk() is GasRisk.WATCH


def test_the_thresholds_can_be_moved_but_not_crossed_over():
    assert GasReading(775, 760).risk(watch_at=10, hazard_at=20) is GasRisk.WATCH
    with pytest.raises(ValidationError):
        GasReading(775, 760).risk(watch_at=80, hazard_at=20)


def test_the_compensation_depth_answers_how_deep_is_deep_enough():
    assert quantize(compensation_depth(40).amount, 3) == Decimal("0.545")
    assert compensation_depth(40).symbol == "m"


def test_water_that_is_not_supersaturated_needs_no_depth():
    assert compensation_depth(0).amount == Decimal(0)
    assert compensation_depth(-20).amount == Decimal(0)


def test_blending_a_bad_well_into_a_good_spring_weights_by_flow():
    parts = [
        (GasReading(800, 760), Quantity(100, "gpm")),
        (GasReading(760, 760), Quantity(300, "gpm")),
    ]
    assert blended_delta_p(parts) == Decimal(10)


def test_blending_nothing_or_no_flow_is_refused():
    with pytest.raises(ValidationError):
        blended_delta_p([])
    with pytest.raises(ValidationError):
        blended_delta_p([(GasReading(800, 760), Quantity(0, "gpm"))])


def test_a_negative_flow_in_a_blend_is_refused():
    with pytest.raises(ValidationError):
        blended_delta_p(
            [
                (GasReading(800, 760), Quantity(-100, "gpm")),
                (GasReading(760, 760), Quantity(300, "gpm")),
            ]
        )
