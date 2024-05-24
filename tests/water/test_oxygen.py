from decimal import Decimal

import pytest

from hatchlot.errors import ValidationError
from hatchlot.numeric import quantize
from hatchlot.quantities.base import Quantity
from hatchlot.quantities.temperature import Temperature
from hatchlot.water.oxygen import (
    available_oxygen,
    barometric_pressure,
    oxygen_deficit,
    percent_saturation,
    saturation_concentration,
    solubility_at,
    vapour_pressure,
)


def test_sea_level_pressure_is_one_atmosphere():
    assert quantize(barometric_pressure(0), 1) == Decimal("760.0")


def test_pressure_falls_with_altitude():
    assert barometric_pressure(1000) < barometric_pressure(0)
    assert quantize(barometric_pressure(1500), 0) == Decimal("634")


def test_an_elevation_no_hatchery_sits_at_is_refused():
    with pytest.raises(ValidationError):
        barometric_pressure(9000)


def test_the_solubility_table_is_read_straight_on_a_whole_degree():
    assert solubility_at(Temperature(10, "C")) == Decimal("11.29")
    assert solubility_at(Temperature(0, "C")) == Decimal("14.62")
    assert solubility_at(Temperature(30, "C")) == Decimal("7.56")


def test_between_two_rows_the_table_interpolates():
    assert solubility_at(Temperature("10.5", "C")) == Decimal("11.16")


def test_a_fahrenheit_reading_finds_the_same_row():
    assert solubility_at(Temperature(50, "F")) == Decimal("11.29")


@pytest.mark.parametrize("celsius", ["-0.1", "30.1"])
def test_outside_the_table_is_refused_rather_than_extrapolated(celsius):
    with pytest.raises(ValidationError):
        solubility_at(Temperature(celsius, "C"))


def test_vapour_pressure_is_small_but_not_nothing():
    assert Decimal(9) < vapour_pressure(Temperature(10, "C")) < Decimal(10)
    assert vapour_pressure(Temperature(20, "C")) > vapour_pressure(Temperature(10, "C"))


def test_vapour_pressure_outside_the_fit_is_refused():
    with pytest.raises(ValidationError):
        vapour_pressure(Temperature(80, "C"))


def test_saturation_at_sea_level_is_the_table_value():
    assert quantize(saturation_concentration(Temperature(10, "C")), 2) == Decimal("11.29")


def test_altitude_costs_the_water_oxygen():
    high = saturation_concentration(Temperature(10, "C"), elevation_m=1500)
    assert high < Decimal("11.29")
    assert quantize(high, 1) == Decimal("9.4")


def test_a_measured_barometer_reading_wins_over_the_elevation():
    assert saturation_concentration(
        Temperature(10, "C"), elevation_m=1500, pressure_mmHg=760
    ) == saturation_concentration(Temperature(10, "C"))


@pytest.mark.parametrize("pressure", [0, "-5"])
def test_an_impossible_barometer_reading_is_refused(pressure):
    with pytest.raises(ValidationError):
        saturation_concentration(Temperature(10, "C"), pressure_mmHg=pressure)


def test_a_pressure_below_the_vapour_pressure_is_refused():
    with pytest.raises(ValidationError):
        saturation_concentration(Temperature(10, "C"), pressure_mmHg=5)


def test_a_reading_at_saturation_is_a_hundred_percent():
    assert quantize(percent_saturation("11.29", Temperature(10, "C")), 0) == Decimal("100")


def test_a_supersaturated_reading_goes_over_a_hundred():
    assert percent_saturation(13, Temperature(10, "C")) > Decimal(100)


def test_a_negative_oxygen_reading_is_refused():
    with pytest.raises(ValidationError):
        percent_saturation(-1, Temperature(10, "C"))


def test_the_deficit_is_how_far_under_saturation_the_water_sits():
    assert quantize(oxygen_deficit(9, Temperature(10, "C")), 2) == Decimal("2.29")


def test_a_supersaturated_reading_has_no_deficit():
    assert oxygen_deficit(13, Temperature(10, "C")) == Decimal(0)


def test_the_available_oxygen_is_what_is_left_above_the_floor():
    delivered = available_oxygen(Quantity(100, "gpm"), "10.0", "6.0")
    assert delivered.symbol == "kg"
    assert quantize(delivered.amount, 3) == Decimal("0.091")


def test_no_headroom_means_no_oxygen_available():
    assert available_oxygen(Quantity(100, "gpm"), 8, 8).amount == Decimal(0)


def test_a_floor_above_the_inflow_is_refused():
    with pytest.raises(ValidationError):
        available_oxygen(Quantity(100, "gpm"), 6, 8)
