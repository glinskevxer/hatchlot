from decimal import Decimal

import pytest

from hatchlot.errors import ConversionError, UnitError
from hatchlot.numeric import quantize
from hatchlot.units import Dimension, System, convert, known_units, preferred, unit


def test_unknown_unit_names_itself():
    with pytest.raises(UnitError) as excinfo:
        unit("furlong")
    assert "furlong" in str(excinfo.value)


def test_identical_units_pass_the_value_through():
    assert convert("12.5", "gpm", "gpm") == Decimal("12.5")


def test_length_round_trips_through_the_base_unit():
    assert quantize(convert(convert(37, "in", "mm"), "mm", "in"), 6) == Decimal("37")


def test_a_foot_is_twelve_inches():
    assert quantize(convert(1, "ft", "in"), 6) == Decimal("12")


def test_a_pound_is_sixteen_ounces():
    assert quantize(convert(1, "lb", "oz"), 6) == Decimal("16")


def test_a_cubic_foot_of_water_holds_about_seven_and_a_half_gallons():
    assert quantize(convert(1, "ft3", "gal"), 3) == Decimal("7.481")


def test_freezing_and_boiling_land_where_they_should():
    assert quantize(convert(32, "F", "C"), 6) == Decimal("0")
    assert quantize(convert(212, "F", "C"), 6) == Decimal("100")
    assert quantize(convert(100, "C", "F"), 6) == Decimal("212")


def test_the_temperature_scales_cross_at_forty_below():
    assert quantize(convert(-40, "F", "C"), 6) == Decimal("-40")


def test_a_hatchery_water_temperature_converts_the_way_the_wall_chart_says():
    assert quantize(convert("50", "F", "C"), 1) == Decimal("10.0")


def test_gallons_per_minute_to_litres_per_minute():
    assert quantize(convert(100, "gpm", "Lpm"), 4) == Decimal("378.5412")


def test_a_cubic_foot_per_second_is_about_four_hundred_and_fifty_gpm():
    assert quantize(convert(1, "cfs", "gpm"), 1) == Decimal("448.8")


def test_pressure_converts_between_the_three_forms_a_barometer_is_read_in():
    assert quantize(convert(1, "atm", "mmHg"), 1) == Decimal("760.0")
    assert quantize(convert(760, "mmHg", "kPa"), 2) == Decimal("101.33")


def test_crossing_a_dimension_is_refused_and_says_which_two():
    with pytest.raises(ConversionError) as excinfo:
        convert(5, "gpm", "lb")
    assert "flow" in str(excinfo.value)
    assert "mass" in str(excinfo.value)


def test_known_units_is_sorted_and_filterable():
    everything = known_units()
    assert everything == tuple(sorted(everything))
    assert set(known_units(Dimension.TEMPERATURE)) == {"C", "F"}


@pytest.mark.parametrize("dimension", list(Dimension))
@pytest.mark.parametrize("system", list(System))
def test_every_dimension_has_a_preferred_unit_in_both_systems(dimension, system):
    assert preferred(dimension, system) in known_units(dimension)


def test_the_us_system_reports_flow_in_gpm_and_metric_in_lpm():
    assert preferred(Dimension.FLOW, System.US) == "gpm"
    assert preferred(Dimension.FLOW, System.METRIC) == "Lpm"


def test_unit_objects_expose_their_system_so_a_report_can_group_them():
    assert unit("ft").system is System.US
    assert unit("mm").system is System.METRIC
    assert unit("mgL").system is None


def test_fifty_fahrenheit_is_exactly_ten_celsius_with_no_repeating_tail():
    assert convert(50, "F", "C") == Decimal("10")


def test_a_cubic_metre_per_hour_is_exactly_one_sixtieth_of_a_thousand_litres():
    assert convert(6, "m3ph", "Lpm") == Decimal("100")
    assert convert(100, "Lpm", "m3ph") == Decimal("6")
