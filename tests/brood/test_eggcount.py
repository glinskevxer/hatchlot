from decimal import Decimal

import pytest

from hatchlot.brood.eggcount import (
    CountMethod,
    EggEstimate,
    displacement_count,
    egg_diameter,
    egg_volume,
    eggs_per_litre,
    gravimetric_count,
    reconcile,
    von_bayer_count,
)
from hatchlot.errors import ValidationError
from hatchlot.numeric import quantize
from hatchlot.quantities.base import Quantity


def test_the_trough_count_gives_the_diameter():
    assert egg_diameter(30) == Quantity("0.4", "in")
    assert quantize(egg_diameter(48).to("mm").amount, 2) == Decimal("6.35")


def test_a_trough_count_of_nothing_is_refused():
    with pytest.raises(ValidationError):
        egg_diameter(0)


def test_the_volume_of_one_egg_is_a_sphere():
    volume = egg_volume(Quantity(6, "mm"))
    assert quantize(volume.amount * Decimal(1000), 4) == Decimal("0.1131")


def test_an_egg_of_no_diameter_is_refused():
    with pytest.raises(ValidationError):
        egg_volume(Quantity(0, "mm"))


def test_bigger_eggs_pack_fewer_to_a_litre():
    assert eggs_per_litre(Quantity(6, "mm")) > eggs_per_litre(Quantity(8, "mm"))


def test_the_packing_fraction_can_be_the_station_s_own():
    default = eggs_per_litre(Quantity(6, "mm"))
    tighter = eggs_per_litre(Quantity(6, "mm"), packing_fraction="0.7")
    assert tighter > default


@pytest.mark.parametrize("bad", [0, "-0.1", "1.1"])
def test_an_impossible_packing_fraction_is_refused(bad):
    with pytest.raises(ValidationError):
        eggs_per_litre(Quantity(6, "mm"), packing_fraction=bad)


def test_a_von_bayer_count_scales_with_the_volume_measured():
    one = von_bayer_count(30, Quantity(1, "L"))
    ten = von_bayer_count(30, Quantity(10, "L"))
    assert quantize(ten / one, 6) == Decimal(10)


def test_a_von_bayer_count_of_a_chinook_take_lands_where_it_should():
    count = von_bayer_count(30, Quantity(1, "L"))
    assert Decimal(1000) < count < Decimal(3000)


def test_a_von_bayer_count_of_no_volume_is_refused():
    with pytest.raises(ValidationError):
        von_bayer_count(30, Quantity(0, "L"))


def test_displacement_counts_the_eggs_and_not_the_gaps():
    count = displacement_count(Quantity(1, "L"), Quantity(6, "mm"))
    assert quantize(count, 0) == Decimal(8842)


def test_displacement_refuses_nothing_displaced():
    with pytest.raises(ValidationError):
        displacement_count(Quantity(0, "L"), Quantity(6, "mm"))


def test_the_gravimetric_method_scales_a_counted_sample():
    assert gravimetric_count(100, Quantity(50, "g"), Quantity(5, "kg")) == Decimal(10000)


@pytest.mark.parametrize("bad", [0, "-1"])
def test_a_gravimetric_sample_of_nothing_is_refused(bad):
    with pytest.raises(ValidationError):
        gravimetric_count(bad, Quantity(50, "g"), Quantity(5, "kg"))
    with pytest.raises(ValidationError):
        gravimetric_count(100, Quantity(bad, "g"), Quantity(5, "kg"))


def test_an_estimate_rounds_to_whole_eggs_for_the_form():
    assert EggEstimate("4321.6", CountMethod.VON_BAYER).rounded == 4322


def test_an_estimate_of_no_eggs_or_no_method_is_refused():
    with pytest.raises(ValidationError):
        EggEstimate(0, CountMethod.VON_BAYER)
    with pytest.raises(ValidationError):
        EggEstimate(100, "von_bayer")  # type: ignore[arg-type]


def test_only_an_enumerated_count_is_not_an_estimate():
    assert CountMethod.ENUMERATED.is_estimate is False
    assert CountMethod.VON_BAYER.is_estimate


def test_two_methods_agree_inside_the_tolerance():
    first = EggEstimate(10000, CountMethod.VON_BAYER)
    second = EggEstimate(10300, CountMethod.DISPLACEMENT)
    assert first.agrees_with(second)
    assert not first.agrees_with(EggEstimate(11000, CountMethod.DISPLACEMENT))


def test_the_tolerance_can_be_widened():
    first = EggEstimate(10000, CountMethod.VON_BAYER)
    assert first.agrees_with(EggEstimate(11000, CountMethod.DISPLACEMENT), tolerance_percent=15)


def test_a_hand_count_wins_over_every_estimate():
    estimates = [
        EggEstimate(10000, CountMethod.VON_BAYER),
        EggEstimate(9000, CountMethod.ENUMERATED),
    ]
    assert reconcile(estimates).eggs == Decimal(9000)


def test_two_estimates_that_agree_are_averaged_not_picked_from():
    estimates = [
        EggEstimate(10000, CountMethod.VON_BAYER),
        EggEstimate(10200, CountMethod.DISPLACEMENT),
    ]
    assert reconcile(estimates).eggs == Decimal(10100)


def test_estimates_that_disagree_are_refused_rather_than_averaged():
    estimates = [
        EggEstimate(10000, CountMethod.VON_BAYER),
        EggEstimate(12000, CountMethod.DISPLACEMENT),
    ]
    with pytest.raises(ValidationError):
        reconcile(estimates)


def test_a_single_estimate_stands_on_its_own():
    only = EggEstimate(10000, CountMethod.VON_BAYER)
    assert reconcile([only]) is only


def test_reconciling_nothing_is_refused():
    with pytest.raises(ValidationError):
        reconcile([])
