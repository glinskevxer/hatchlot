from decimal import Decimal

import pytest

from hatchlot.errors import ValidationError
from hatchlot.marking.mark import (
    MarkPlan,
    MarkType,
    TagCode,
    is_double_index,
    mark_rate,
)


def plan(marks=(MarkType.ADIPOSE_CLIP,), code=None, rate="1.0"):
    return MarkPlan(
        lot="2024-CHK-01",
        marks=tuple(marks),
        tag_code=TagCode(code) if code else None,
        target_rate=Decimal(rate),
    )


def test_a_clip_is_the_mark_an_angler_can_see():
    assert MarkType.ADIPOSE_CLIP.is_external
    assert not MarkType.CODED_WIRE_TAG.is_external
    assert MarkType.CODED_WIRE_TAG.carries_a_code
    assert not MarkType.ADIPOSE_CLIP.carries_a_code
    assert MarkType.CODED_WIRE_TAG.needs_detection


@pytest.mark.parametrize("text", ["05-12-34", "05 12 34", " 05/12/34 "])
def test_a_tag_code_reads_the_forms_it_is_written_in(text):
    assert str(TagCode(text)) == "05-12-34"


@pytest.mark.parametrize("bad", ["", "05-12", "5-12-34-1", "ab-12-34", "05-12-00", "00-12-34"])
def test_a_malformed_tag_code_is_refused(bad):
    with pytest.raises(ValidationError):
        TagCode(bad)


def test_tag_codes_sort_by_agency_then_year_then_series():
    codes = [TagCode("05-12-34"), TagCode("05-11-99"), TagCode("04-99-99")]
    assert [str(code) for code in sorted(codes)][0] == "04-99-99"


def test_the_next_series_in_the_same_year():
    assert str(TagCode("05-12-34").successor()) == "05-12-35"
    with pytest.raises(ValidationError):
        TagCode("05-12-99").successor()


def test_a_tag_code_knows_its_agency():
    assert TagCode("05-12-34").belongs_to(5)
    assert not TagCode("05-12-34").belongs_to(6)


def test_a_plan_with_no_marks_is_not_a_plan():
    with pytest.raises(ValidationError):
        plan(marks=())


def test_a_mark_type_that_is_not_one_is_refused():
    with pytest.raises(ValidationError):
        MarkPlan(lot="2024-CHK-01", marks=("adipose_clip",))  # type: ignore[arg-type]


def test_a_mark_is_applied_once():
    with pytest.raises(ValidationError):
        plan(marks=(MarkType.ADIPOSE_CLIP, MarkType.ADIPOSE_CLIP))


def test_a_coded_wire_tag_plan_needs_a_code():
    with pytest.raises(ValidationError):
        plan(marks=(MarkType.CODED_WIRE_TAG,))
    assert plan(marks=(MarkType.CODED_WIRE_TAG,), code="05-12-34").needs_a_code


def test_a_target_rate_outside_a_share_is_refused():
    with pytest.raises(ValidationError):
        plan(rate="0")
    with pytest.raises(ValidationError):
        plan(rate="1.5")


def test_a_plan_with_a_clip_is_visible_and_one_without_is_not():
    assert plan().is_visible
    assert not plan(marks=(MarkType.PIT_TAG,)).is_visible


def test_how_many_fish_the_plan_says_to_mark():
    assert plan(rate="1.0").fish_to_mark(50000) == Decimal(50000)
    assert plan(rate="0.25").fish_to_mark(50000) == Decimal(12500)
    with pytest.raises(ValidationError):
        plan().fish_to_mark(0)


def test_a_part_fish_rounds_to_a_whole_one():
    assert plan(rate="0.5").fish_to_mark(1001) == Decimal(501)


def test_the_mark_rate_of_a_group():
    assert mark_rate(25000, 50000) == Decimal("0.5")
    with pytest.raises(ValidationError):
        mark_rate(60000, 50000)
    with pytest.raises(ValidationError):
        mark_rate(1000, 0)


def test_a_double_index_group_carries_both_marks():
    both = plan(marks=(MarkType.ADIPOSE_CLIP, MarkType.CODED_WIRE_TAG), code="05-12-34")
    assert is_double_index(both)
    assert not is_double_index(plan())
    assert not is_double_index(plan(marks=(MarkType.CODED_WIRE_TAG,), code="05-12-34"))
