from decimal import Decimal

import pytest

from hatchlot.errors import ValidationError
from hatchlot.numeric import quantize
from hatchlot.permits.effluent import (
    concentration_from,
    estimate_loading,
    feed_ceiling,
    parameter_mass,
    projected_against,
)
from hatchlot.permits.limits import Basis, Limit, Parameter
from hatchlot.quantities.base import Quantity


def limit(value="5", basis=Basis.CONCENTRATION, parameter=Parameter.SUSPENDED_SOLIDS):
    return Limit(parameter=parameter, basis=basis, value=Decimal(value))


def test_a_month_of_feeding_turns_into_a_loading():
    loading = estimate_loading(Quantity(1000, "kg"))
    assert loading.solids == Quantity("250.00", "kg")
    assert loading.phosphorus == Quantity("5.5000", "kg")
    assert loading.nitrogen == Quantity("38.5000", "kg")


def test_the_shares_can_be_the_station_s_own():
    loading = estimate_loading(Quantity(1000, "kg"), solids_share="0.3")
    assert loading.solids == Quantity("300.0", "kg")


def test_an_impossible_share_or_a_negative_feed_is_refused():
    with pytest.raises(ValidationError):
        estimate_loading(Quantity(1000, "kg"), solids_share="1.5")
    with pytest.raises(ValidationError):
        estimate_loading(Quantity(-1, "kg"))


def test_the_total_and_the_daily_split_of_a_loading():
    loading = estimate_loading(Quantity(1000, "kg"))
    assert loading.total > loading.solids
    assert loading.per_day(10) == Quantity(25, "kg")
    with pytest.raises(ValidationError):
        loading.per_day(0)


def test_a_mass_at_a_flow_over_days_is_a_concentration():
    value = concentration_from(Quantity(250, "kg"), Quantity(1000, "Lpm"), 30)
    assert quantize(value, 4) == Decimal("5.7870")


def test_a_bigger_flow_dilutes_the_same_mass():
    small = concentration_from(Quantity(250, "kg"), Quantity(500, "Lpm"), 30)
    big = concentration_from(Quantity(250, "kg"), Quantity(2000, "Lpm"), 30)
    assert big < small


def test_a_concentration_needs_days_and_a_flow():
    with pytest.raises(ValidationError):
        concentration_from(Quantity(250, "kg"), Quantity(1000, "Lpm"), 0)
    with pytest.raises(ValidationError):
        concentration_from(Quantity(250, "kg"), Quantity(0, "Lpm"), 30)


def test_the_feed_a_permit_allows():
    ceiling = feed_ceiling(limit(value="5"), Quantity(1000, "Lpm"), 30)
    assert quantize(ceiling.to("kg").amount, 0) == Decimal(864)


def test_feeding_at_the_ceiling_lands_on_the_limit():
    ceiling = feed_ceiling(limit(value="5"), Quantity(1000, "Lpm"), 30)
    loading = estimate_loading(ceiling)
    share = projected_against(loading, limit(value="5"), Quantity(1000, "Lpm"), 30)
    assert quantize(share, 4) == Decimal("1.0000")


def test_a_ceiling_only_makes_sense_against_a_concentration_limit():
    with pytest.raises(ValidationError):
        feed_ceiling(limit(basis=Basis.MASS_PER_DAY), Quantity(1000, "Lpm"), 30)
    with pytest.raises(ValidationError):
        feed_ceiling(limit(), Quantity(1000, "Lpm"), 0)
    with pytest.raises(ValidationError):
        feed_ceiling(limit(), Quantity(1000, "Lpm"), 30, share=0)


def test_the_part_of_a_loading_that_answers_a_parameter():
    loading = estimate_loading(Quantity(1000, "kg"))
    assert parameter_mass(loading, Parameter.SUSPENDED_SOLIDS) == loading.solids
    assert parameter_mass(loading, Parameter.SETTLEABLE_SOLIDS) == loading.solids
    assert parameter_mass(loading, Parameter.TOTAL_PHOSPHORUS) == loading.phosphorus
    assert parameter_mass(loading, Parameter.TOTAL_AMMONIA) == loading.nitrogen


def test_a_parameter_the_feed_model_says_nothing_about():
    loading = estimate_loading(Quantity(1000, "kg"))
    with pytest.raises(ValidationError):
        parameter_mass(loading, Parameter.BOD)


def test_the_projection_against_a_limit_is_a_share_of_it():
    loading = estimate_loading(Quantity(1000, "kg"))
    share = projected_against(loading, limit(value="5"), Quantity(1000, "Lpm"), 30)
    assert share > Decimal(1)
    generous = projected_against(loading, limit(value="20"), Quantity(1000, "Lpm"), 30)
    assert generous < Decimal(1)


def test_a_projection_against_a_mass_limit_is_refused():
    loading = estimate_loading(Quantity(1000, "kg"))
    with pytest.raises(ValidationError):
        projected_against(loading, limit(basis=Basis.MASS_PER_DAY), Quantity(1000, "Lpm"), 30)
