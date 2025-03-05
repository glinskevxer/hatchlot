from decimal import Decimal

import pytest

from hatchlot.distribution.haul import (
    HaulLoad,
    OxygenSupply,
    Tank,
    check_tempering,
    haul_density,
    loads_needed,
    oxygen_needed,
    tank_capacity,
    tempering_minutes,
    tempering_span,
)
from hatchlot.errors import PolicyError, ValidationError
from hatchlot.numeric import quantize
from hatchlot.quantities.base import Quantity
from hatchlot.quantities.temperature import Temperature


def tank(code="TK-1", litres="3000", supply=OxygenSupply.BOTTLED):
    return Tank(code=code, volume=Quantity(litres, "L"), supply=supply)


def load(fish="20000", grams="20", hours="4", celsius="10", tanks=None):
    return HaulLoad(
        code="HL-001",
        tanks=tanks or [tank()],
        fish=Decimal(fish),
        mean_weight=Quantity(grams, "g"),
        hours=Decimal(hours),
        load_water=Temperature(celsius, "C"),
        driver="jt",
    )


def test_a_tank_normalises_its_code_and_needs_a_volume():
    assert tank(code=" tk 1 ").code == "TK-1"
    with pytest.raises(ValidationError):
        tank(litres="0")
    with pytest.raises(ValidationError):
        Tank(code="TK-1", volume=Quantity(100, "L"), supply="bottled")  # type: ignore[arg-type]


def test_only_a_bottled_or_liquid_supply_can_be_topped_up():
    assert OxygenSupply.BOTTLED.can_be_topped_up
    assert not OxygenSupply.AGITATOR.can_be_topped_up


def test_a_longer_trip_carries_fewer_fish():
    short = haul_density(1, Temperature(10, "C"))
    long_haul = haul_density(8, Temperature(10, "C"))
    assert long_haul < short


def test_warmer_water_carries_fewer_fish():
    cold = haul_density(4, Temperature(8, "C"))
    warm = haul_density(4, Temperature(16, "C"))
    assert warm < cold


def test_cold_water_gets_no_bonus_above_the_base():
    assert haul_density(4, Temperature(4, "C")) == haul_density(4, Temperature(10, "C"))


def test_the_heat_derate_stops_at_a_floor():
    assert haul_density(4, Temperature(30, "C")) == haul_density(4, Temperature(40, "C"))


def test_an_impossible_trip_is_refused():
    with pytest.raises(ValidationError):
        haul_density(0, Temperature(10, "C"))
    with pytest.raises(ValidationError):
        haul_density(4, Temperature(0, "C"))


def test_the_biomass_a_tank_will_carry():
    capacity = tank_capacity(tank(litres="3000"), 4, Temperature(10, "C"))
    assert quantize(capacity.to("kg").amount, 1) == Decimal("240.0")


def test_the_oxygen_a_load_uses():
    used = oxygen_needed(Quantity(400, "kg"), 4)
    assert quantize(used.to("kg").amount, 3) == Decimal("0.720")
    with pytest.raises(ValidationError):
        oxygen_needed(Quantity(0, "kg"), 4)
    with pytest.raises(ValidationError):
        oxygen_needed(Quantity(400, "kg"), 0)


def test_a_haul_needs_tanks_fish_hours_and_a_driver():
    with pytest.raises(ValidationError):
        HaulLoad(
            code="HL-1",
            tanks=[],
            fish=Decimal(100),
            mean_weight=Quantity(20, "g"),
            hours=Decimal(4),
            load_water=Temperature(10, "C"),
            driver="jt",
        )
    with pytest.raises(ValidationError):
        load(fish="0")
    with pytest.raises(ValidationError):
        load(hours="0")
    with pytest.raises(ValidationError):
        HaulLoad(
            code="HL-1",
            tanks=[tank()],
            fish=Decimal(100),
            mean_weight=Quantity(20, "g"),
            hours=Decimal(4),
            load_water=Temperature(10, "C"),
            driver=" ",
        )


def test_the_same_tank_twice_is_refused():
    with pytest.raises(ValidationError):
        load(tanks=[tank(), tank()])


def test_the_water_and_the_biomass_of_a_load():
    entry = load(
        fish="20000", grams="20", tanks=[tank(litres="3000"), tank(code="TK-2", litres="2000")]
    )
    assert entry.water_volume == Quantity(5000, "L")
    assert entry.biomass == Quantity("400.000", "kg")


def test_a_load_inside_its_capacity_passes_the_check():
    entry = load(fish="10000", grams="20")
    assert not entry.is_overloaded
    assert entry.loading_share < Decimal(1)
    entry.check()


def test_an_overloaded_truck_is_refused_by_name():
    entry = load(fish="40000", grams="20")
    assert entry.is_overloaded
    with pytest.raises(PolicyError) as excinfo:
        entry.check()
    assert excinfo.value.rule == "haul.overloaded"


def test_the_oxygen_a_load_will_need():
    entry = load(fish="20000", grams="20", hours="4")
    assert quantize(entry.oxygen().to("kg").amount, 3) == Decimal("0.720")


def test_how_far_apart_the_two_waters_are():
    gap = tempering_span(Temperature(10, "C"), Temperature(14, "C"))
    assert gap.degrees == Decimal(4)
    assert tempering_span(Temperature(14, "C"), Temperature(10, "C")).degrees == Decimal(4)


def test_how_long_the_tempering_takes():
    assert tempering_minutes(Temperature(10, "C"), Temperature(14, "C")) == 40
    assert tempering_minutes(Temperature(10, "C"), Temperature(14, "C"), minutes_per_degree=5) == 20
    assert tempering_minutes(Temperature(10, "C"), Temperature(10, "C")) == 0


def test_a_tempering_rate_of_nothing_is_refused():
    with pytest.raises(ValidationError):
        tempering_minutes(Temperature(10, "C"), Temperature(14, "C"), minutes_per_degree=0)


def test_a_release_across_too_big_a_step_is_refused_by_name():
    check_tempering(Temperature(10, "C"), Temperature(11, "C"))
    with pytest.raises(PolicyError) as excinfo:
        check_tempering(Temperature(10, "C"), Temperature(15, "C"))
    assert excinfo.value.rule == "haul.tempering"


def test_the_step_limit_can_be_widened():
    check_tempering(Temperature(10, "C"), Temperature(15, "C"), limit_celsius=6)
    with pytest.raises(ValidationError):
        check_tempering(Temperature(10, "C"), Temperature(11, "C"), limit_celsius=0)


def test_how_many_loads_a_release_takes():
    trips = loads_needed(100000, Quantity(20, "g"), tank(litres="3000"), 4, Temperature(10, "C"))
    assert trips == 9


def test_a_release_that_fits_in_one_load():
    assert loads_needed(1000, Quantity(20, "g"), tank(litres="3000"), 4, Temperature(10, "C")) == 1


def test_a_release_of_nothing_is_refused():
    with pytest.raises(ValidationError):
        loads_needed(0, Quantity(20, "g"), tank(), 4, Temperature(10, "C"))
