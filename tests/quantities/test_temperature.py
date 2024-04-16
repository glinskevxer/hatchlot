from decimal import Decimal

import pytest

from hatchlot.errors import ValidationError
from hatchlot.quantities.temperature import (
    Temperature,
    TemperatureSpan,
    mean_temperature,
    span_between,
)
from hatchlot.units import System


def test_a_reading_converts_both_ways():
    assert Temperature(50, "F").celsius == Decimal(10)
    assert Temperature(10, "C").fahrenheit == Decimal(50)


def test_below_absolute_zero_is_refused_on_either_scale():
    with pytest.raises(ValidationError):
        Temperature("-300", "C")
    with pytest.raises(ValidationError):
        Temperature("-500", "F")


def test_an_unknown_scale_is_refused():
    with pytest.raises(ValidationError):
        Temperature(10, "K")


def test_two_readings_subtract_to_a_span_not_a_reading():
    difference = Temperature(55, "F") - Temperature(50, "F")
    assert isinstance(difference, TemperatureSpan)
    assert difference.degrees == Decimal(5)


def test_the_span_converts_by_ratio_which_is_the_whole_point():
    difference = Temperature(55, "F") - Temperature(50, "F")
    assert difference.to("C").degrees == Decimal(5) / Decimal("1.8")
    assert TemperatureSpan(5, "C").to("F").degrees == Decimal(9)


def test_a_span_added_to_a_reading_is_a_reading():
    warmed = Temperature(50, "F") + TemperatureSpan(5, "F")
    assert isinstance(warmed, Temperature)
    assert warmed.value == Decimal(55)


def test_a_span_subtracted_from_a_reading_is_a_reading():
    cooled = Temperature(10, "C") - TemperatureSpan("1.5", "C")
    assert isinstance(cooled, Temperature)
    assert cooled.value == Decimal("8.5")


def test_a_cross_scale_span_lands_on_the_reading_correctly():
    warmed = Temperature(10, "C") + TemperatureSpan("1.8", "F")
    assert warmed.rounded(4).value == Decimal("11.0000")


def test_span_arithmetic_stays_in_the_left_hand_scale():
    total = TemperatureSpan(2, "C") + TemperatureSpan("1.8", "F")
    assert total.scale == "C"
    assert total.degrees == Decimal(3)
    assert (TemperatureSpan(3, "C") - TemperatureSpan(1, "C")).degrees == Decimal(2)
    assert (TemperatureSpan(2, "C") * 3).degrees == Decimal(6)


def test_span_negation_and_absolute_value():
    assert (-TemperatureSpan(2, "C")).degrees == Decimal(-2)
    assert abs(TemperatureSpan(-2, "C")).degrees == Decimal(2)


def test_spans_compare_across_scales():
    assert TemperatureSpan(1, "C") > TemperatureSpan(1, "F")
    assert TemperatureSpan(1, "C") >= TemperatureSpan("1.8", "F")
    assert TemperatureSpan(1, "F") < TemperatureSpan(1, "C")
    assert TemperatureSpan(1, "F") <= TemperatureSpan(1, "C")
    assert TemperatureSpan(1, "C") == TemperatureSpan("1.8", "F")


def test_spans_hash_by_their_size_not_their_scale():
    assert len({TemperatureSpan(1, "C"), TemperatureSpan("1.8", "F")}) == 1


def test_a_span_does_not_compare_equal_to_a_bare_number():
    assert TemperatureSpan(1, "C") != 1


def test_readings_compare_across_scales():
    assert Temperature(50, "F") == Temperature(10, "C")
    assert Temperature(49, "F") < Temperature(10, "C")
    assert Temperature(51, "F") > Temperature(10, "C")
    assert Temperature(50, "F") <= Temperature(10, "C")
    assert Temperature(50, "F") >= Temperature(10, "C")
    assert len({Temperature(50, "F"), Temperature(10, "C")}) == 1


def test_a_reading_does_not_compare_equal_to_a_span():
    assert Temperature(10, "C") != TemperatureSpan(10, "C")


def test_in_system_hands_a_us_station_fahrenheit():
    assert Temperature(10, "C").in_system(System.US).scale == "F"
    assert Temperature(50, "F").in_system(System.METRIC).scale == "C"


def test_to_the_same_scale_is_the_same_object():
    reading = Temperature(10, "C")
    assert reading.to("C") is reading
    span = TemperatureSpan(1, "C")
    assert span.to("C") is span


def test_rounding_a_reading_keeps_its_scale():
    assert Temperature("50.267", "F").rounded(1).value == Decimal("50.3")
    assert Temperature("50.267", "F").rounded().scale == "F"


def test_printing_reads_like_a_log_sheet():
    assert str(Temperature("50.50", "F")) == "50.5 degF"
    assert str(TemperatureSpan("2.00", "C")) == "2 degC"


@pytest.mark.parametrize("text", ["52.3 F", " 52.3F ", "52.3 degF", "52.3°F"])
def test_parse_reads_the_forms_people_actually_write(text):
    assert Temperature.parse(text) == Temperature("52.3", "F")


@pytest.mark.parametrize("bad", ["", "52.3", "52.3 K", "   "])
def test_parse_refuses_a_reading_with_no_usable_scale(bad):
    with pytest.raises(ValidationError):
        Temperature.parse(bad)


def test_mean_of_readings_taken_on_both_scales():
    readings = [Temperature(50, "F"), Temperature(10, "C"), Temperature(52, "F")]
    assert mean_temperature(readings, "F").rounded(2).value == Decimal("50.67")


def test_mean_of_nothing_is_refused():
    with pytest.raises(ValidationError):
        mean_temperature([])


def test_mean_refuses_an_unknown_scale():
    with pytest.raises(ValidationError):
        mean_temperature([Temperature(10, "C")], "K")


def test_span_between_is_positive_whichever_way_round_it_is_asked():
    hot = Temperature(55, "F")
    cold = Temperature(50, "F")
    assert span_between(cold, hot, "F").degrees == Decimal(5)
    assert span_between(hot, cold, "F").degrees == Decimal(5)
