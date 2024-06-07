from decimal import Decimal
from typing import Any

import pytest

from hatchlot.errors import ValidationError
from hatchlot.numeric import quantize
from hatchlot.quantities.temperature import Temperature
from hatchlot.water.quality import (
    QualityFlag,
    QualityLimits,
    WaterQuality,
    ammonia_pka,
    nitrite_chloride_ratio,
    total_ammonia_ceiling,
    unionised_ammonia,
    unionised_fraction,
)


def test_the_dissociation_constant_falls_as_the_water_warms():
    assert ammonia_pka(Temperature(10, "C")) > ammonia_pka(Temperature(20, "C"))
    assert quantize(ammonia_pka(Temperature(10, "C")), 2) == Decimal("9.73")


def test_the_unionised_share_is_small_at_the_ph_a_hatchery_runs_at():
    fraction = unionised_fraction("7.0", Temperature(10, "C"))
    assert Decimal("0.001") < fraction < Decimal("0.005")


def test_a_pH_unit_higher_is_roughly_ten_times_the_danger():
    low = unionised_fraction("7.0", Temperature(10, "C"))
    high = unionised_fraction("8.0", Temperature(10, "C"))
    assert Decimal(8) < high / low < Decimal(11)


def test_warm_water_makes_the_same_reading_worse():
    cold = unionised_fraction("7.5", Temperature(6, "C"))
    warm = unionised_fraction("7.5", Temperature(16, "C"))
    assert warm > cold


@pytest.mark.parametrize("bad", ["3.9", "11.1"])
def test_a_pH_no_water_has_is_refused(bad):
    with pytest.raises(ValidationError):
        unionised_fraction(bad, Temperature(10, "C"))


def test_the_unionised_concentration_is_the_total_times_the_share():
    total = Decimal("1.0")
    share = unionised_fraction("8.0", Temperature(12, "C"))
    assert unionised_ammonia(total, "8.0", Temperature(12, "C")) == total * share


def test_a_negative_ammonia_reading_is_refused():
    with pytest.raises(ValidationError):
        unionised_ammonia("-0.1", 7, Temperature(10, "C"))


def test_the_wall_chart_ceiling_inverts_the_calculation():
    ceiling = total_ammonia_ceiling("0.0125", "8.0", Temperature(12, "C"))
    assert quantize(unionised_ammonia(ceiling, "8.0", Temperature(12, "C")), 4) == Decimal("0.0125")


def test_the_ceiling_drops_as_the_water_gets_more_alkaline():
    warm = Temperature(12, "C")
    assert total_ammonia_ceiling("0.0125", "8.5", warm) < total_ammonia_ceiling(
        "0.0125", "7.0", warm
    )


def test_the_nitrite_ratio_needs_chloride_to_divide_by():
    assert nitrite_chloride_ratio("0.5", "10") == Decimal("0.05")
    with pytest.raises(ValidationError):
        nitrite_chloride_ratio("0.5", 0)


def test_a_negative_nitrite_reading_is_refused():
    with pytest.raises(ValidationError):
        nitrite_chloride_ratio("-0.5", 10)


def test_an_inverted_ph_band_is_refused():
    with pytest.raises(ValidationError):
        QualityLimits(ph_low=Decimal(9), ph_high=Decimal(7))


def test_a_marginal_share_outside_a_fraction_is_refused():
    with pytest.raises(ValidationError):
        QualityLimits(marginal_share=Decimal("1.5"))
    with pytest.raises(ValidationError):
        QualityLimits(marginal_share=Decimal(0))


def test_the_three_bands_of_one_limit():
    limits = QualityLimits()
    assert limits.flag_against("0.005", Decimal("0.0125")) is QualityFlag.OK
    assert limits.flag_against("0.011", Decimal("0.0125")) is QualityFlag.MARGINAL
    assert limits.flag_against("0.02", Decimal("0.0125")) is QualityFlag.OVER


def clean(**overrides: Any) -> WaterQuality:
    values: dict[str, Any] = {
        "ph": Decimal("7.0"),
        "temperature": Temperature(10, "C"),
        "total_ammonia_mgL": Decimal("0.5"),
        "nitrite_mgL": Decimal("0.05"),
        "chloride_mgL": Decimal(20),
    }
    values.update(overrides)
    return WaterQuality(**values)


def test_a_clean_sample_flags_nothing():
    assert clean().worst_flag() is QualityFlag.OK


def test_a_reading_at_a_high_ph_turns_the_same_ammonia_into_a_problem():
    assert clean(ph=Decimal("8.5")).flags()["ammonia"] is QualityFlag.OVER
    assert clean(ph=Decimal("8.5")).worst_flag() is QualityFlag.OVER


def test_nitrite_is_only_judged_when_there_is_a_chloride_reading():
    assert "nitrite" in clean().flags()
    assert "nitrite" not in clean(chloride_mgL=Decimal(0)).flags()


def test_a_nitrite_ratio_over_the_limit_is_flagged():
    assert clean(nitrite_mgL=Decimal(5)).flags()["nitrite"] is QualityFlag.OVER


def test_a_ph_outside_the_band_is_flagged_on_its_own_account():
    assert clean(ph=Decimal("6.0"), total_ammonia_mgL=Decimal(0)).flags()["ph"] is QualityFlag.OVER
    assert clean(ph=Decimal("9.5"), total_ammonia_mgL=Decimal(0)).flags()["ph"] is QualityFlag.OVER


def test_a_sample_refuses_a_negative_reading_and_an_impossible_ph():
    with pytest.raises(ValidationError):
        clean(total_ammonia_mgL=Decimal("-1"))
    with pytest.raises(ValidationError):
        clean(ph=Decimal(12))
