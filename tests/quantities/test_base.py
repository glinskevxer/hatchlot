from decimal import Decimal

import pytest

from hatchlot.errors import ConversionError, UnitError, ValidationError
from hatchlot.quantities.base import Quantity, as_quantity, sum_quantities
from hatchlot.units import Dimension, System


def test_a_quantity_knows_what_it_measures():
    assert Quantity(12, "gpm").dimension is Dimension.FLOW


def test_an_unknown_unit_is_refused_at_construction():
    with pytest.raises(UnitError):
        Quantity(1, "hogshead")


def test_conversion_keeps_the_amount_and_changes_the_unit():
    assert Quantity(1, "ft").to("in").amount == Decimal("12")


def test_arithmetic_answers_in_the_left_hand_unit():
    total = Quantity(1, "ft") + Quantity(6, "in")
    assert total.symbol == "ft"
    assert total.rounded(3).amount == Decimal("1.500")


def test_subtraction_across_units_lines_up_first():
    assert (Quantity(1, "ft") - Quantity(6, "in")).rounded(2).amount == Decimal("0.50")


def test_adding_a_different_dimension_is_refused():
    with pytest.raises(ConversionError):
        Quantity(1, "ft") + Quantity(1, "lb")


def test_scaling_and_dividing_keep_the_unit():
    assert (Quantity(10, "lb") * 3).amount == Decimal("30")
    assert (Quantity(10, "lb") / 4).amount == Decimal("2.5")


def test_dividing_by_zero_names_the_divisor():
    with pytest.raises(ValidationError):
        Quantity(1, "lb") / 0


def test_negation_and_absolute_value():
    assert (-Quantity(3, "lb")).amount == Decimal("-3")
    assert abs(Quantity("-3.5", "lb")).amount == Decimal("3.5")


def test_equality_looks_through_the_unit():
    assert Quantity(1, "ft") == Quantity(12, "in")
    assert Quantity(1, "ft") != Quantity(11, "in")


def test_equality_against_another_dimension_is_false_not_an_error():
    assert Quantity(1, "ft") != Quantity(1, "lb")


def test_equality_against_a_non_quantity_defers():
    assert Quantity(1, "ft") != "1 ft"


def test_equal_quantities_hash_together_whatever_unit_they_are_in():
    assert len({Quantity(1, "ft"), Quantity(12, "in"), Quantity(24, "in")}) == 2


def test_ordering_converts_before_it_compares():
    assert Quantity(11, "in") < Quantity(1, "ft")
    assert Quantity(12, "in") <= Quantity(1, "ft")
    assert Quantity(13, "in") > Quantity(1, "ft")
    assert Quantity(12, "in") >= Quantity(1, "ft")


def test_sorting_a_mixed_unit_list_works_because_ordering_converts():
    values = [Quantity(2, "ft"), Quantity(3, "in"), Quantity(30, "cm")]
    assert [q.symbol for q in sorted(values)] == ["in", "cm", "ft"]


def test_in_system_picks_the_unit_the_station_reports_in():
    assert Quantity(1, "m").in_system(System.US).symbol == "in"
    assert Quantity(1, "ft").in_system(System.METRIC).symbol == "mm"


def test_printing_is_what_a_person_would_write():
    assert str(Quantity("12.50", "gpm")) == "12.5 gpm"
    assert str(Quantity(0, "gpm")) == "0 gpm"


def test_repr_round_trips_through_eval_shaped_text():
    assert repr(Quantity("2.5", "lb")) == "Quantity('2.5', 'lb')"


def test_parse_reads_what_is_written_on_a_clipboard():
    assert Quantity.parse(" 12.5  gpm ") == Quantity("12.5", "gpm")


@pytest.mark.parametrize("bad", ["12.5", "", "12.5 gpm extra"])
def test_parse_refuses_anything_that_is_not_amount_then_unit(bad):
    with pytest.raises(ValidationError):
        Quantity.parse(bad)


def test_as_tuple_is_storable_and_loses_nothing():
    amount, symbol = Quantity("2.500", "lb").as_tuple()
    assert (amount, symbol) == ("2.500", "lb")
    assert Quantity(amount, symbol) == Quantity("2.5", "lb")


def test_sum_quantities_totals_into_one_unit():
    total = sum_quantities([Quantity(1, "ft"), Quantity(6, "in"), Quantity(30, "cm")], "in")
    assert total.symbol == "in"
    assert total.rounded(2).amount == Decimal("29.81")


def test_sum_quantities_of_nothing_is_zero_in_the_asked_unit():
    assert sum_quantities([], "lb") == Quantity(0, "lb")


def test_as_quantity_takes_either_form():
    assert as_quantity(5, "lb") == Quantity(5, "lb")
    assert as_quantity(Quantity(1, "kg"), "lb").rounded(4).amount == Decimal("2.2046")
