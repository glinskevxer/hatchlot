from decimal import Decimal

import pytest

from hatchlot.errors import ValidationError
from hatchlot.quantities.base import Quantity
from hatchlot.reporting.tables import (
    Align,
    Column,
    bullet_list,
    heading,
    join_sections,
    render_pairs,
    render_table,
)


def columns():
    return [
        Column(heading="lot"),
        Column(heading="fish", align=Align.RIGHT),
        Column(heading="weight", align=Align.RIGHT, places=2),
    ]


def test_a_table_has_a_heading_a_rule_and_its_rows():
    text = render_table(columns(), [["2024-CHK-01", Decimal(50000), Quantity("2.5", "g")]])
    lines = text.splitlines()
    assert lines[0].startswith("lot")
    assert set(lines[1]) <= {"-", " "}
    assert "2024-CHK-01" in lines[2]


def test_numbers_go_right_and_text_goes_left():
    text = render_table(columns(), [["a", Decimal(1), Quantity(1, "g")]])
    lines = text.splitlines()
    assert lines[2].startswith("a")
    assert lines[0].index("fish") > lines[0].index("lot")


def test_a_column_wider_than_its_heading_widens_rather_than_cutting_off():
    text = render_table([Column(heading="lot")], [["a-very-long-lot-code-indeed"]])
    assert "a-very-long-lot-code-indeed" in text


def test_a_quantity_prints_with_its_unit_and_the_column_rounding():
    column = Column(heading="weight", places=1)
    assert column.render(Quantity("2.55", "g")) == "2.6 g"
    assert Column(heading="weight").render(Quantity("2.50", "g")) == "2.5 g"


def test_a_decimal_prints_to_the_column_places():
    assert Column(heading="x", places=2).render(Decimal("1.005")) == "1.01"
    assert Column(heading="x").render(Decimal("1.500")) == "1.5"


def test_a_boolean_prints_as_yes_or_no_and_none_prints_as_nothing():
    column = Column(heading="ok")
    assert column.render(True) == "yes"
    assert column.render(False) == "no"
    assert column.render(None) == ""


def test_anything_else_prints_as_itself():
    assert Column(heading="x").render("RW-1") == "RW-1"
    assert Column(heading="x").render(7) == "7"


def test_a_column_needs_a_heading_a_real_alignment_and_sane_places():
    with pytest.raises(ValidationError):
        Column(heading="  ")
    with pytest.raises(ValidationError):
        Column(heading="x", align="left")  # type: ignore[arg-type]
    with pytest.raises(ValidationError):
        Column(heading="x", places=-1)


def test_a_table_with_no_columns_or_a_ragged_row_is_refused():
    with pytest.raises(ValidationError):
        render_table([], [])
    with pytest.raises(ValidationError):
        render_table(columns(), [["a", Decimal(1)]])


def test_a_table_with_no_rows_still_has_its_heading():
    text = render_table(columns(), [])
    assert len(text.splitlines()) == 2


def test_no_line_has_trailing_whitespace():
    text = render_table(columns(), [["a", Decimal(1), Quantity(1, "g")]])
    assert all(line == line.rstrip() for line in text.splitlines())


def test_a_pair_block_lines_the_labels_up():
    text = render_pairs([("station", "Cold Creek"), ("lots", Decimal(12))])
    lines = text.splitlines()
    assert lines[0].startswith("station")
    assert lines[1].startswith("lots   ")


def test_a_pair_block_of_nothing_is_refused():
    with pytest.raises(ValidationError):
        render_pairs([])


def test_a_heading_gets_a_rule_the_same_width():
    text = heading("Production report")
    lines = text.splitlines()
    assert lines[1] == "=" * len(lines[0])
    assert heading("x", underline="-").splitlines()[1] == "-"


def test_a_heading_needs_words_and_a_single_underline_character():
    with pytest.raises(ValidationError):
        heading("   ")
    with pytest.raises(ValidationError):
        heading("x", underline="==")


def test_a_bullet_list_and_an_empty_one():
    assert bullet_list(["one", "two"]) == "- one\n- two"
    assert bullet_list([]) == ""
    assert bullet_list(["one"], marker="*") == "* one"


def test_sections_join_with_blank_lines_and_drop_the_empty_ones():
    text = join_sections(["first", "", "  ", "second"])
    assert text == "first\n\nsecond"
    assert join_sections([]) == ""
