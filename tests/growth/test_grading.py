from decimal import Decimal

import pytest

from hatchlot.errors import ValidationError
from hatchlot.growth.grading import (
    Distribution,
    SizeClass,
    describe,
    grade,
    graded_share,
    split_at,
)
from hatchlot.numeric import quantize
from hatchlot.quantities.base import Quantity


def grams(*values):
    return [Quantity(str(value), "g") for value in values]


def test_a_size_class_is_closed_at_the_bottom_and_open_at_the_top():
    small = SizeClass("small", Quantity(1, "g"), Quantity(5, "g"))
    assert small.holds(Quantity(1, "g"))
    assert small.holds(Quantity("4.99", "g"))
    assert not small.holds(Quantity(5, "g"))


def test_a_size_class_needs_a_name_and_a_band_the_right_way_round():
    with pytest.raises(ValidationError):
        SizeClass(" ", Quantity(1, "g"), Quantity(5, "g"))
    with pytest.raises(ValidationError):
        SizeClass("small", Quantity(5, "g"), Quantity(1, "g"))
    with pytest.raises(ValidationError):
        SizeClass("small", Quantity(0, "g"), Quantity(5, "g"))


def test_a_distribution_reports_the_mean_and_the_spread():
    found = describe(grams(2, 3, 4, 5))
    assert found.count == 4
    assert found.mean == Quantity("3.5", "g")
    assert found.smallest_g == Decimal(2)
    assert found.largest_g == Decimal(5)


def test_a_tight_lot_is_uniform_and_a_ragged_one_wants_grading():
    tight = describe(grams(10, 10, 11, 10, 9, 10))
    ragged = describe(grams(2, 5, 9, 14, 20, 3))
    assert tight.is_uniform()
    assert not tight.wants_grading()
    assert not ragged.is_uniform()
    assert ragged.wants_grading()


def test_the_limits_can_be_moved():
    ragged = describe(grams(2, 5, 9, 14, 20, 3))
    assert ragged.is_uniform(limit="0.9")
    assert not ragged.wants_grading(limit="0.9")


def test_the_range_ratio_is_what_the_crew_sees_in_the_net():
    found = describe(grams(2, 4, 6, 8))
    assert found.range_ratio == Decimal(4)


def test_a_distribution_needs_more_than_one_fish():
    with pytest.raises(ValidationError):
        describe(grams(5))
    with pytest.raises(ValidationError):
        describe([])


def test_a_weightless_fish_in_the_sample_is_refused():
    with pytest.raises(ValidationError):
        describe(grams(5, 0))


def classes():
    return [
        SizeClass("small", Quantity(1, "g"), Quantity(5, "g")),
        SizeClass("medium", Quantity(5, "g"), Quantity(10, "g")),
        SizeClass("large", Quantity(10, "g"), Quantity(20, "g")),
    ]


def test_grading_counts_a_sample_into_its_classes():
    counts = grade(grams(2, 3, 6, 7, 12), classes())
    assert counts["small"] == 2
    assert counts["medium"] == 2
    assert counts["large"] == 1
    assert counts["ungraded"] == 0


def test_fish_outside_every_class_are_counted_as_ungraded():
    counts = grade(grams("0.5", 25), classes())
    assert counts["ungraded"] == 2


def test_grading_into_no_classes_is_refused():
    with pytest.raises(ValidationError):
        grade(grams(2, 3), [])


def test_the_classes_are_taken_in_size_order_however_they_are_passed():
    shuffled = list(reversed(classes()))
    counts = grade(grams(2, 6, 12), shuffled)
    assert counts["small"] == 1
    assert counts["large"] == 1


def test_the_share_that_fell_in_a_class():
    counts = grade(grams(2, 3, 6, 7), classes())
    assert graded_share(counts, "small") == Decimal("0.5")
    with pytest.raises(ValidationError):
        graded_share(counts, "jumbo")
    with pytest.raises(ValidationError):
        graded_share({"small": 0}, "small")


def test_the_median_split_is_the_mean_of_a_symmetric_lot():
    found = describe(grams(8, 9, 10, 11, 12))
    assert split_at(found, "0.5") == Quantity(10, "g")


def test_a_low_split_falls_below_the_mean_and_a_high_one_above():
    found = describe(grams(8, 9, 10, 11, 12))
    assert split_at(found, "0.25") < Quantity(10, "g")
    assert split_at(found, "0.75") > Quantity(10, "g")


def test_the_split_table_is_interpolated_between_its_rows():
    found = describe(grams(8, 9, 10, 11, 12))
    between = split_at(found, "0.6")
    assert Quantity(10, "g") < between < split_at(found, "0.75")


def test_an_extreme_split_is_pulled_back_to_the_ends_of_the_table():
    found = describe(grams(8, 9, 10, 11, 12))
    assert split_at(found, "0.01") == split_at(found, "0.1")
    assert split_at(found, "0.99") == split_at(found, "0.9")


def test_a_split_share_outside_the_range_is_refused():
    found = describe(grams(8, 9, 10, 11, 12))
    with pytest.raises(ValidationError):
        split_at(found, 0)
    with pytest.raises(ValidationError):
        split_at(found, 1)


def test_a_split_that_would_fall_below_zero_weight_is_refused():
    wild = Distribution(
        count=4,
        mean_g=Decimal(2),
        spread_g=Decimal(10),
        smallest_g=Decimal(1),
        largest_g=Decimal(30),
    )
    with pytest.raises(ValidationError):
        split_at(wild, "0.1")


def test_the_coefficient_of_variation_of_a_known_spread():
    found = describe(grams(9, 11))
    assert quantize(found.coefficient_of_variation, 2) == Decimal("0.10")
