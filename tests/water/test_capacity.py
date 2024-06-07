from decimal import Decimal
from typing import Any

import pytest

from hatchlot.errors import ValidationError
from hatchlot.numeric import quantize
from hatchlot.quantities.base import Quantity
from hatchlot.quantities.temperature import Temperature
from hatchlot.water.capacity import (
    BindingLimit,
    carrying_capacity,
    density_limited_biomass,
    flow_limited_biomass,
    oxygen_consumption_rate,
    oxygen_limited_biomass,
)


def test_small_fish_breathe_harder_per_kilogram_than_big_ones():
    warm = Temperature(12, "C")
    assert oxygen_consumption_rate(warm, 2) > oxygen_consumption_rate(warm, 40)


def test_warm_water_costs_more_oxygen_than_cold():
    assert oxygen_consumption_rate(Temperature(14, "C"), 10) > oxygen_consumption_rate(
        Temperature(8, "C"), 10
    )


def test_the_consumption_model_lands_where_the_fitted_constants_put_it():
    assert quantize(oxygen_consumption_rate(Temperature(10, "C"), 10), 1) == Decimal("302.1")


def test_a_weightless_fish_is_refused():
    with pytest.raises(ValidationError):
        oxygen_consumption_rate(Temperature(10, "C"), 0)


def test_the_station_can_pass_its_own_fitted_coefficients():
    default = oxygen_consumption_rate(Temperature(10, "C"), 10)
    fitted = oxygen_consumption_rate(Temperature(10, "C"), 10, scale=300)
    assert fitted > default


def test_the_oxygen_limit_is_the_available_oxygen_over_what_the_fish_use():
    biomass = oxygen_limited_biomass(Quantity(100, "gpm"), "10.0", "6.0", Temperature(10, "C"), 10)
    assert biomass.symbol == "kg"
    assert quantize(biomass.amount, 1) == Decimal("300.7")


def test_more_headroom_carries_more_fish():
    warm = Temperature(10, "C")
    tight = oxygen_limited_biomass(Quantity(100, "gpm"), 9, 6, warm, 10)
    loose = oxygen_limited_biomass(Quantity(100, "gpm"), 11, 6, warm, 10)
    assert loose > tight


def test_no_headroom_or_no_flow_is_refused():
    with pytest.raises(ValidationError):
        oxygen_limited_biomass(Quantity(100, "gpm"), 6, 6, Temperature(10, "C"), 10)
    with pytest.raises(ValidationError):
        oxygen_limited_biomass(Quantity(0, "gpm"), 10, 6, Temperature(10, "C"), 10)


def test_the_flow_index_limit_is_index_times_flow_times_length():
    biomass = flow_limited_biomass(Quantity(100, "gpm"), Quantity(4, "in"), "1.5")
    assert biomass == Quantity(600, "lb")


def test_the_density_index_limit_is_index_times_volume_times_length():
    biomass = density_limited_biomass(Quantity(500, "ft3"), Quantity(4, "in"), "0.5")
    assert biomass == Quantity(1000, "lb")


@pytest.mark.parametrize("index", [0, "-1"])
def test_an_index_of_zero_or_less_is_refused(index):
    with pytest.raises(ValidationError):
        flow_limited_biomass(Quantity(100, "gpm"), Quantity(4, "in"), index)
    with pytest.raises(ValidationError):
        density_limited_biomass(Quantity(500, "ft3"), Quantity(4, "in"), index)


def test_a_fish_of_no_length_is_refused():
    with pytest.raises(ValidationError):
        flow_limited_biomass(Quantity(100, "gpm"), Quantity(0, "in"), 1)


def base_capacity(**overrides: object):
    arguments: dict[str, Any] = {
        "flow": Quantity(200, "gpm"),
        "volume": Quantity(600, "ft3"),
        "length": Quantity(4, "in"),
        "inflow_mgL": "10.0",
        "floor_mgL": "6.0",
        "temperature": Temperature(10, "C"),
        "fish_weight_g": 10,
        "flow_index": "1.5",
        "density_index": "0.5",
    }
    arguments.update(overrides)
    return carrying_capacity(**arguments)


def test_all_three_limits_are_reported_not_just_the_binding_one():
    capacity = base_capacity()
    assert capacity.oxygen.symbol == "lb"
    assert capacity.flow_index == Quantity(1200, "lb")
    assert capacity.density_index == Quantity(1200, "lb")


def test_a_short_flow_makes_the_flow_index_bind():
    capacity = base_capacity(flow=Quantity(60, "gpm"), volume=Quantity(5000, "ft3"))
    assert capacity.binding is BindingLimit.FLOW_INDEX
    assert capacity.allowed == Quantity(360, "lb")


def test_a_small_box_on_plenty_of_water_makes_density_bind():
    capacity = base_capacity(volume=Quantity(50, "ft3"), flow=Quantity(400, "gpm"))
    assert capacity.binding is BindingLimit.DENSITY_INDEX
    assert capacity.allowed == Quantity(100, "lb")


def test_warm_water_with_a_high_floor_makes_oxygen_bind():
    capacity = base_capacity(temperature=Temperature(16, "C"), inflow_mgL="8.0", floor_mgL="6.5")
    assert capacity.binding is BindingLimit.OXYGEN
    assert capacity.allowed < Quantity(1200, "lb")


def test_headroom_goes_negative_when_the_unit_is_over():
    capacity = base_capacity(flow=Quantity(60, "gpm"), volume=Quantity(5000, "ft3"))
    assert capacity.headroom(Quantity(300, "lb")) == Quantity(60, "lb")
    assert capacity.headroom(Quantity(400, "lb")) == Quantity(-40, "lb")
    assert capacity.is_over(Quantity(400, "lb"))
    assert not capacity.is_over(Quantity(360, "lb"))


def test_headroom_takes_a_biomass_in_any_mass_unit():
    capacity = base_capacity(flow=Quantity(60, "gpm"), volume=Quantity(5000, "ft3"))
    assert quantize(capacity.headroom(Quantity(100, "kg")).amount, 1) == Decimal("139.5")
