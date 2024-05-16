from decimal import Decimal

import pytest

from hatchlot.errors import DuplicateError, NotFoundError, ValidationError
from hatchlot.quantities.base import Quantity
from hatchlot.quantities.temperature import Temperature
from hatchlot.water.source import (
    BlendPart,
    SourceKind,
    SourceRegister,
    WaterSource,
    blend_flow,
    blend_temperature,
    mix_fraction,
)


def spring(code="SP-1", flow="900", minimum=None, kind=SourceKind.SPRING):
    return WaterSource(
        code=code,
        name=f"source {code}",
        kind=kind,
        design_flow=Quantity(flow, "gpm"),
        minimum_flow=None if minimum is None else Quantity(minimum, "gpm"),
    )


def test_a_source_normalises_its_code():
    assert spring(code=" sp 1 ").code == "SP-1"


def test_a_nameless_source_is_refused():
    with pytest.raises(ValidationError):
        WaterSource(code="X", name=" ", kind=SourceKind.WELL, design_flow=Quantity(1, "gpm"))


def test_a_kind_that_is_not_a_kind_is_refused():
    with pytest.raises(ValidationError):
        WaterSource(
            code="X",
            name="X",
            kind="well",  # type: ignore[arg-type]
            design_flow=Quantity(1, "gpm"),
        )


def test_a_negative_design_flow_is_refused():
    with pytest.raises(ValidationError):
        spring(flow="-1")


def test_a_minimum_above_the_design_flow_is_refused():
    with pytest.raises(ValidationError):
        spring(flow="500", minimum="600")


def test_the_dependable_flow_is_the_minimum_when_there_is_one():
    assert spring(flow="900", minimum="400").dependable_flow == Quantity(400, "gpm")
    assert spring(flow="900").dependable_flow == Quantity(900, "gpm")


def test_the_shortfall_is_never_negative():
    source = spring(flow="900", minimum="400")
    assert source.shortfall_against(Quantity(500, "gpm")) == Quantity(100, "gpm")
    assert source.shortfall_against(Quantity(300, "gpm")) == Quantity(0, "gpm")


def test_surface_and_reuse_water_are_the_ones_that_carry_a_pathogen():
    assert SourceKind.SURFACE.is_pathogen_bearing
    assert SourceKind.REUSE.is_pathogen_bearing
    assert not SourceKind.WELL.is_pathogen_bearing
    assert not SourceKind.SPRING.is_pathogen_bearing


def test_a_blend_is_weighted_by_flow_not_by_how_many_pipes_there_are():
    parts = [
        BlendPart("SP-1", Quantity(900, "gpm"), Temperature(11, "C")),
        BlendPart("WL-1", Quantity(100, "gpm"), Temperature(6, "C")),
    ]
    assert blend_temperature(parts).rounded(2).value == Decimal("10.50")


def test_a_blend_can_be_asked_for_in_fahrenheit():
    parts = [
        BlendPart("SP-1", Quantity(1, "gpm"), Temperature(50, "F")),
        BlendPart("WL-1", Quantity(1, "gpm"), Temperature(60, "F")),
    ]
    assert blend_temperature(parts, "F").rounded(1).value == Decimal("55.0")


def test_blending_across_flow_units_lines_them_up_first():
    parts = [
        BlendPart("SP-1", Quantity(100, "gpm"), Temperature(10, "C")),
        BlendPart("WL-1", Quantity("378.5412", "Lpm"), Temperature(14, "C")),
    ]
    assert blend_temperature(parts).rounded(2).value == Decimal("12.00")


def test_blending_nothing_is_refused():
    with pytest.raises(ValidationError):
        blend_temperature([])


def test_a_blend_of_closed_valves_has_no_temperature():
    parts = [BlendPart("SP-1", Quantity(0, "gpm"), Temperature(11, "C"))]
    with pytest.raises(ValidationError):
        blend_temperature(parts)


def test_a_negative_contribution_is_refused():
    with pytest.raises(ValidationError):
        BlendPart("SP-1", Quantity(-5, "gpm"), Temperature(11, "C"))


def test_the_total_flow_of_a_blend_adds_up_in_one_unit():
    parts = [
        BlendPart("SP-1", Quantity(100, "gpm"), Temperature(10, "C")),
        BlendPart("WL-1", Quantity(100, "gpm"), Temperature(10, "C")),
    ]
    assert blend_flow(parts) == Quantity(200, "gpm")
    assert blend_flow(parts, "Lpm").rounded(2).amount == Decimal("757.08")


def test_the_share_of_one_source_in_a_blend():
    parts = [
        BlendPart("SP-1", Quantity(750, "gpm"), Temperature(10, "C")),
        BlendPart("WL-1", Quantity(250, "gpm"), Temperature(6, "C")),
    ]
    assert mix_fraction(parts, "sp 1") == Decimal("0.75")
    assert mix_fraction(parts, "WL-1") == Decimal("0.25")
    assert mix_fraction(parts, "CK-1") == Decimal(0)


def test_the_share_of_a_blend_with_no_flow_is_refused():
    parts = [BlendPart("SP-1", Quantity(0, "gpm"), Temperature(10, "C"))]
    with pytest.raises(ValidationError):
        mix_fraction(parts, "SP-1")


def test_the_register_refuses_a_second_source_on_one_code():
    register = SourceRegister()
    register.add(spring())
    with pytest.raises(DuplicateError):
        register.add(spring())


def test_the_register_looks_up_through_the_sloppy_form_of_a_code():
    register = SourceRegister()
    register.add(spring())
    assert register.get(" sp 1 ").code == "SP-1"
    assert "sp-1" in register
    assert 7 not in register
    with pytest.raises(NotFoundError):
        register.get("SP-9")


def test_the_register_lists_in_code_order_and_by_kind():
    register = SourceRegister()
    register.add(spring(code="WL-1", kind=SourceKind.WELL))
    register.add(spring(code="SP-1"))
    assert [s.code for s in register.all()] == ["SP-1", "WL-1"]
    assert [s.code for s in register.of_kind(SourceKind.WELL)] == ["WL-1"]
    assert len(register) == 2


def test_the_dependable_total_uses_minimums_where_they_exist():
    register = SourceRegister()
    register.add(spring(code="SP-1", flow="900", minimum="400"))
    register.add(spring(code="WL-1", flow="300", kind=SourceKind.WELL))
    assert register.total_dependable_flow() == Quantity(700, "gpm")


def test_the_reuse_fraction_of_a_station_with_no_reuse_is_zero():
    register = SourceRegister()
    register.add(spring())
    assert register.reuse_fraction() == Decimal(0)
    assert SourceRegister().reuse_fraction() == Decimal(0)


def test_the_reuse_fraction_counts_only_reused_water():
    register = SourceRegister()
    register.add(spring(code="SP-1", flow="750"))
    register.add(spring(code="RU-1", flow="250", kind=SourceKind.REUSE))
    assert register.reuse_fraction() == Decimal("0.25")
