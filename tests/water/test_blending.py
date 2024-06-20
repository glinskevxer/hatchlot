from decimal import Decimal

import pytest

from hatchlot.errors import ValidationError
from hatchlot.quantities.base import Quantity
from hatchlot.water.blending import flow_share, flow_weighted, total_flow


def part(flow, value, tag="a"):
    return (Quantity(flow, "gpm"), Decimal(str(value)), tag)


PARTS = [part(900, 11), part(100, 6, tag="b")]


def flow_of(item):
    return item[0]


def value_of(item):
    return item[1]


def test_the_mean_is_weighted_by_flow():
    assert flow_weighted(PARTS, flow_of, value_of) == Decimal("10.5")


def test_a_mix_in_two_flow_units_lines_up_first():
    parts = [
        (Quantity(100, "gpm"), Decimal(10), "a"),
        (Quantity("378.5412", "Lpm"), Decimal(14), "b"),
    ]
    assert flow_weighted(parts, flow_of, value_of).quantize(Decimal("0.01")) == Decimal("12.00")


def test_blending_nothing_names_what_was_asked_for():
    with pytest.raises(ValidationError) as excinfo:
        flow_weighted([], flow_of, value_of, what="gas blend")
    assert "gas blend" in str(excinfo.value)


def test_a_mix_with_the_valves_shut_has_no_value():
    with pytest.raises(ValidationError):
        flow_weighted([part(0, 11)], flow_of, value_of)


def test_a_negative_contribution_is_refused_everywhere():
    bad = [part(-100, 11), part(300, 6)]
    with pytest.raises(ValidationError):
        flow_weighted(bad, flow_of, value_of)
    with pytest.raises(ValidationError):
        total_flow(bad, flow_of, "gpm")
    with pytest.raises(ValidationError):
        flow_share(bad, flow_of, lambda _: True)


def test_the_total_adds_up_in_the_asked_unit():
    assert total_flow(PARTS, flow_of, "gpm") == Quantity(1000, "gpm")
    assert total_flow([], flow_of, "gpm") == Quantity(0, "gpm")


def test_the_share_of_the_matching_items():
    assert flow_share(PARTS, flow_of, lambda item: item[2] == "a") == Decimal("0.9")
    assert flow_share(PARTS, flow_of, lambda _: False) == Decimal(0)


def test_the_share_of_a_mix_with_no_flow_is_refused():
    with pytest.raises(ValidationError):
        flow_share([part(0, 11)], flow_of, lambda _: True)
