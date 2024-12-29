from decimal import Decimal

import pytest

from hatchlot.errors import PolicyError, ValidationError
from hatchlot.health.treatment import (
    Chemical,
    Method,
    Treatment,
    check_concentration,
    check_oxygen,
    flush_dose,
    oxygen_headroom_needed,
    safe_ceiling,
    static_dose,
)
from hatchlot.numeric import quantize
from hatchlot.quantities.base import Quantity
from hatchlot.quantities.temperature import Temperature


def static(concentration="167", minutes="60", chemical=Chemical.FORMALIN, celsius="10"):
    return Treatment(
        lot="2024-CHK-01",
        chemical=chemical,
        method=Method.STATIC,
        concentration_ppm=Decimal(concentration),
        minutes=Decimal(minutes),
        water=Temperature(celsius, "C"),
        volume=Quantity(90, "m3"),
    )


def flush(concentration="167", minutes="60", chemical=Chemical.FORMALIN, celsius="10"):
    return Treatment(
        lot="2024-CHK-01",
        chemical=chemical,
        method=Method.FLUSH,
        concentration_ppm=Decimal(concentration),
        minutes=Decimal(minutes),
        water=Temperature(celsius, "C"),
        flow=Quantity(500, "gpm"),
    )


def test_the_ceiling_falls_as_the_water_warms():
    cold = safe_ceiling(Chemical.FORMALIN, Temperature(8, "C"))
    warm = safe_ceiling(Chemical.FORMALIN, Temperature(16, "C"))
    assert cold == Decimal(250)
    assert warm < cold


def test_salt_has_no_temperature_derate():
    cold = safe_ceiling(Chemical.SALT, Temperature(8, "C"))
    warm = safe_ceiling(Chemical.SALT, Temperature(20, "C"))
    assert cold == warm


def test_the_derate_stops_at_a_fifth_of_the_ceiling():
    scalding = safe_ceiling(Chemical.FORMALIN, Temperature(40, "C"))
    assert scalding == Decimal(250) * Decimal("0.2")


def test_a_chemical_that_is_not_a_chemical_is_refused():
    with pytest.raises(ValidationError):
        safe_ceiling("formalin", Temperature(10, "C"))  # type: ignore[arg-type]


def test_a_concentration_over_the_ceiling_is_refused_by_name():
    with pytest.raises(PolicyError) as excinfo:
        check_concentration(Chemical.FORMALIN, 300, Temperature(10, "C"))
    assert excinfo.value.rule == "treatment.concentration"
    check_concentration(Chemical.FORMALIN, 167, Temperature(10, "C"))


def test_the_same_concentration_can_pass_cold_and_fail_warm():
    check_concentration(Chemical.FORMALIN, 200, Temperature(8, "C"))
    with pytest.raises(PolicyError):
        check_concentration(Chemical.FORMALIN, 200, Temperature(18, "C"))


def test_a_static_dose_is_the_concentration_times_the_volume():
    dose = static_dose(167, Quantity(90, "m3"))
    assert quantize(dose.to("kg").amount, 3) == Decimal("15.030")


def test_a_flush_dose_is_the_concentration_times_the_water_that_passes():
    dose = flush_dose(167, Quantity(500, "gpm"), 60)
    assert quantize(dose.to("kg").amount, 2) == Decimal("18.96")


def test_the_two_sums_do_not_agree_which_is_the_whole_point():
    assert static_dose(167, Quantity(90, "m3")) != flush_dose(167, Quantity(500, "gpm"), 60)


@pytest.mark.parametrize("bad", [0, "-1"])
def test_an_impossible_dose_is_refused(bad):
    with pytest.raises(ValidationError):
        static_dose(bad, Quantity(90, "m3"))
    with pytest.raises(ValidationError):
        flush_dose(167, Quantity(500, "gpm"), bad)


def test_a_static_bath_needs_a_volume_and_a_flush_needs_a_flow():
    with pytest.raises(ValidationError):
        Treatment(
            lot="2024-CHK-01",
            chemical=Chemical.FORMALIN,
            method=Method.STATIC,
            concentration_ppm=Decimal(167),
            minutes=Decimal(60),
            water=Temperature(10, "C"),
        )
    with pytest.raises(ValidationError):
        Treatment(
            lot="2024-CHK-01",
            chemical=Chemical.FORMALIN,
            method=Method.FLUSH,
            concentration_ppm=Decimal(167),
            minutes=Decimal(60),
            water=Temperature(10, "C"),
            volume=Quantity(90, "m3"),
        )


def test_a_treatment_needs_a_real_chemical_method_and_numbers():
    with pytest.raises(ValidationError):
        static(concentration="0")
    with pytest.raises(ValidationError):
        static(minutes="0")
    with pytest.raises(ValidationError):
        Treatment(
            lot="2024-CHK-01",
            chemical="formalin",  # type: ignore[arg-type]
            method=Method.STATIC,
            concentration_ppm=Decimal(167),
            minutes=Decimal(60),
            water=Temperature(10, "C"),
            volume=Quantity(90, "m3"),
        )


def test_the_treatment_picks_the_sum_that_fits_its_method():
    assert static().dose == static_dose(167, Quantity(90, "m3"))
    assert flush().dose == flush_dose(167, Quantity(500, "gpm"), 60)


def test_a_static_bath_is_the_only_method_that_needs_no_flow():
    assert not Method.STATIC.needs_flow
    assert Method.FLUSH.needs_flow
    assert Method.CONSTANT.needs_flow


def test_the_exposure_is_the_product_that_does_the_work():
    assert static(concentration="100", minutes="60").exposure == Decimal(6000)


def test_half_the_concentration_for_twice_as_long_is_the_same_exposure():
    long_soak = static(concentration="100", minutes="60")
    short_hit = static(concentration="200", minutes="30")
    assert long_soak.is_equivalent_to(short_hit)
    assert not long_soak.is_equivalent_to(static(concentration="100", minutes="30"))


def test_a_negative_equivalence_tolerance_is_refused():
    with pytest.raises(ValidationError):
        static().is_equivalent_to(static(), tolerance="-0.1")


def test_a_treatment_checks_its_own_concentration():
    static().check()
    with pytest.raises(PolicyError):
        static(concentration="300").check()


def test_only_formalin_costs_the_water_oxygen():
    assert oxygen_headroom_needed(static(concentration="200")) == Decimal(2)
    assert oxygen_headroom_needed(static(chemical=Chemical.SALT)) == Decimal(0)
    assert Chemical.FORMALIN.consumes_oxygen
    assert not Chemical.SALT.consumes_oxygen


def test_a_treatment_that_would_pull_the_unit_under_its_floor_is_refused():
    with pytest.raises(PolicyError) as excinfo:
        check_oxygen(static(concentration="250"), 8, 6)
    assert excinfo.value.rule == "treatment.oxygen"
    check_oxygen(static(concentration="100"), 10, 6)


def test_an_impossible_oxygen_reading_is_refused():
    with pytest.raises(ValidationError):
        check_oxygen(static(), 0, 6)
