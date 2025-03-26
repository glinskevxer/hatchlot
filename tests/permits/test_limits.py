from decimal import Decimal

import pytest

from hatchlot.errors import ValidationError
from hatchlot.numeric import quantize
from hatchlot.permits.limits import (
    Basis,
    Limit,
    Parameter,
    Sample,
    exceeds,
    feed_allowance,
    headroom,
    limit_for,
    net_removal,
    share_of_limit,
    worst_of,
)
from hatchlot.quantities.base import Quantity


def limit(value="5", basis=Basis.CONCENTRATION, parameter=Parameter.SUSPENDED_SOLIDS, net=True):
    return Limit(parameter=parameter, basis=basis, value=Decimal(value), net=net)


def sample(intake="2", outfall="6", flow="1000", feed=None, parameter=Parameter.SUSPENDED_SOLIDS):
    return Sample(
        parameter=parameter,
        intake=Decimal(intake),
        outfall=Decimal(outfall),
        flow=Quantity(flow, "Lpm") if flow else None,
        feed=Quantity(feed, "kg") if feed else None,
    )


def test_a_parameter_carries_the_unit_it_is_measured_in():
    assert Parameter.SETTLEABLE_SOLIDS.unit == "mlL"
    assert Parameter.SUSPENDED_SOLIDS.unit == "mgL"
    assert Parameter.TOTAL_PHOSPHORUS.is_nutrient
    assert not Parameter.BOD.is_nutrient


def test_a_limit_needs_a_real_parameter_basis_and_value():
    with pytest.raises(ValidationError):
        Limit(parameter="solids", basis=Basis.CONCENTRATION, value=Decimal(5))  # type: ignore[arg-type]
    with pytest.raises(ValidationError):
        Limit(parameter=Parameter.BOD, basis="concentration", value=Decimal(5))  # type: ignore[arg-type]
    with pytest.raises(ValidationError):
        limit(value="0")


def test_the_limit_description_says_net_or_gross():
    assert "net" in limit().description
    assert "gross" in limit(net=False).description


def test_the_net_reading_is_what_the_station_added():
    assert sample(intake="2", outfall="6").net == Decimal(4)
    assert sample(intake="2", outfall="6").gross == Decimal(6)


def test_a_cleaner_outfall_than_intake_reads_as_no_addition():
    assert sample(intake="6", outfall="2").net == Decimal(0)


def test_a_negative_reading_is_refused():
    with pytest.raises(ValidationError):
        sample(intake="-1")
    with pytest.raises(ValidationError):
        sample(outfall="-1")


def test_a_sample_of_the_wrong_parameter_cannot_answer_a_limit():
    with pytest.raises(ValidationError):
        sample(parameter=Parameter.BOD).value_for(limit())


def test_a_concentration_limit_reads_the_net_or_the_gross():
    assert sample().value_for(limit(net=True)) == Decimal(4)
    assert sample().value_for(limit(net=False)) == Decimal(6)


def test_a_mass_limit_turns_the_concentration_into_a_load():
    value = sample(flow="1000").value_for(limit(basis=Basis.MASS_PER_DAY, value="10"))
    assert quantize(value, 3) == Decimal("5.760")


def test_the_same_sample_can_pass_one_basis_and_fail_the_other():
    concentration = limit(value="5", basis=Basis.CONCENTRATION)
    mass = limit(value="3", basis=Basis.MASS_PER_DAY)
    reading = sample(intake="2", outfall="6", flow="1000")
    assert not exceeds(reading, concentration)
    assert exceeds(reading, mass)


def test_a_mass_limit_without_a_flow_is_refused():
    with pytest.raises(ValidationError):
        sample(flow=None).value_for(limit(basis=Basis.MASS_PER_DAY))


def test_a_feed_based_limit_divides_the_load_by_the_feed():
    reading = sample(flow="1000", feed="100")
    value = reading.value_for(limit(basis=Basis.FEED_BASED, value="1"))
    assert quantize(value, 4) == Decimal("0.0576")


def test_a_feed_based_limit_needs_both_the_feed_and_the_flow():
    with pytest.raises(ValidationError):
        sample(flow="1000", feed=None).value_for(limit(basis=Basis.FEED_BASED))
    with pytest.raises(ValidationError):
        sample(flow=None, feed="100").value_for(limit(basis=Basis.FEED_BASED))


def test_the_headroom_and_the_share_of_a_limit():
    reading = sample(intake="2", outfall="6")
    assert headroom(reading, limit(value="5")) == Decimal(1)
    assert headroom(reading, limit(value="3")) == Decimal(-1)
    assert share_of_limit(reading, limit(value="8")) == Decimal("0.5")


def test_what_a_feed_based_limit_allows_for_a_quantity_of_feed():
    allowed = feed_allowance(limit(basis=Basis.FEED_BASED, value="0.5"), Quantity(100, "kg"))
    assert allowed == Decimal(50)


def test_a_limit_that_is_not_feed_based_has_no_feed_allowance():
    with pytest.raises(ValidationError):
        feed_allowance(limit(), Quantity(100, "kg"))
    with pytest.raises(ValidationError):
        feed_allowance(limit(basis=Basis.FEED_BASED), Quantity(0, "kg"))


def test_a_settling_pond_that_works_shows_up_as_a_removal():
    assert net_removal(sample(intake="10", outfall="4")) == Decimal("0.6")
    assert net_removal(sample(intake="10", outfall="15")) == Decimal("-0.5")
    with pytest.raises(ValidationError):
        net_removal(sample(intake="0", outfall="4"))


def test_the_worst_sample_against_a_limit():
    readings = [sample(outfall="6"), sample(outfall="10"), sample(parameter=Parameter.BOD)]
    worst = worst_of(readings, limit())
    assert worst is not None
    assert worst.outfall == Decimal(10)
    assert worst_of([], limit()) is None


def test_finding_the_one_limit_that_covers_a_parameter():
    limits = [
        limit(value="5", basis=Basis.CONCENTRATION),
        limit(value="3", basis=Basis.MASS_PER_DAY),
    ]
    assert limit_for(limits, Parameter.SUSPENDED_SOLIDS, Basis.MASS_PER_DAY).value == Decimal(3)
    with pytest.raises(ValidationError):
        limit_for(limits, Parameter.BOD, Basis.CONCENTRATION)
    with pytest.raises(ValidationError):
        limit_for([*limits, limit(value="9")], Parameter.SUSPENDED_SOLIDS, Basis.CONCENTRATION)
