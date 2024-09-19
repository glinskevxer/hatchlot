from decimal import Decimal

import pytest

from hatchlot.errors import PolicyError, ValidationError
from hatchlot.numeric import quantize
from hatchlot.quantities.base import Quantity
from hatchlot.rearing.sampling import (
    Sample,
    check_sample,
    estimate_biomass,
    estimate_population,
    growth_between,
    summarise_samples,
)

LOT = "2024-CHK-01"


def sample(day="2025-03-01", fish=200, grams="500", lot=LOT):
    return Sample(day, lot, fish, Quantity(grams, "g"), "kt")


def test_a_sample_gives_the_mean_weight_and_the_count_the_crew_talks_in():
    entry = sample(fish=200, grams="500")
    assert entry.mean_weight == Quantity("2.5", "g")
    assert quantize(entry.fish_per_pound, 0) == Decimal(181)


def test_a_sample_of_no_fish_or_no_weight_is_refused():
    with pytest.raises(ValidationError):
        sample(fish=0)
    with pytest.raises(ValidationError):
        sample(grams="0")


def test_a_sample_needs_whoever_took_it():
    with pytest.raises(ValidationError):
        Sample("2025-03-01", LOT, 100, Quantity(100, "g"), " ")


def test_a_small_sample_knows_it_is_small():
    assert sample(fish=200).is_large_enough()
    assert not sample(fish=40).is_large_enough()
    assert sample(fish=40).is_large_enough(minimum=20)


def test_one_sample_has_no_spread_to_report():
    summary = summarise_samples([sample()])
    assert summary.samples == 1
    assert summary.spread == Decimal(0)
    assert summary.coefficient_of_variation == Decimal(0)
    assert summary.is_consistent()


def test_the_mean_is_weighted_by_how_many_fish_each_sample_held():
    big = sample(fish=400, grams="800")
    small = sample(fish=100, grams="300")
    summary = summarise_samples([big, small])
    assert summary.fish == 500
    assert summary.mean_weight == Quantity("2.2", "g")


def test_samples_that_disagree_show_up_in_the_spread():
    tight = summarise_samples([sample(fish=100, grams="250"), sample(fish=100, grams="255")])
    loose = summarise_samples([sample(fish=100, grams="250"), sample(fish=100, grams="400")])
    assert tight.coefficient_of_variation < loose.coefficient_of_variation
    assert tight.is_consistent()
    assert not loose.is_consistent()


def test_the_consistency_limit_can_be_moved():
    loose = summarise_samples([sample(fish=100, grams="250"), sample(fish=100, grams="400")])
    assert loose.is_consistent(limit="0.5")


def test_summarising_nothing_or_a_mixture_of_lots_is_refused():
    with pytest.raises(ValidationError):
        summarise_samples([])
    with pytest.raises(ValidationError):
        summarise_samples([sample(), sample(lot="2024-CHK-02")])


def test_a_sample_too_small_for_the_lot_is_refused_by_name():
    with pytest.raises(PolicyError) as excinfo:
        check_sample(sample(fish=40), 50000)
    assert excinfo.value.rule == "sampling.too_small"


def test_a_big_enough_sample_passes_quietly():
    check_sample(sample(fish=200), 50000)


def test_a_sample_of_the_whole_lot_is_not_a_sample_problem():
    check_sample(sample(fish=40), 40)
    check_sample(sample(fish=40), 30)


def test_a_check_against_no_population_is_refused():
    with pytest.raises(ValidationError):
        check_sample(sample(), 0)


def test_the_population_a_biomass_comes_to():
    assert estimate_population(Quantity(125, "kg"), Quantity("2.5", "g")) == Decimal(50000)
    with pytest.raises(ValidationError):
        estimate_population(Quantity(125, "kg"), Quantity(0, "g"))


def test_the_biomass_a_population_comes_to():
    assert estimate_biomass(50000, Quantity("2.5", "g")) == Quantity("125.000", "kg")
    with pytest.raises(ValidationError):
        estimate_biomass(0, Quantity("2.5", "g"))


def test_growth_between_two_samples():
    first = sample(day="2025-03-01", fish=100, grams="200")
    second = sample(day="2025-04-01", fish=100, grams="300")
    assert growth_between(first, second) == Decimal("0.5")


def test_growth_needs_two_samples_off_one_lot_in_order():
    first = sample(day="2025-03-01")
    with pytest.raises(ValidationError):
        growth_between(first, sample(day="2025-03-01"))
    with pytest.raises(ValidationError):
        growth_between(first, sample(day="2025-04-01", lot="2024-CHK-02"))
