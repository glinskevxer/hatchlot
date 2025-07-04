from decimal import Decimal

import click
import pytest
from click.testing import CliRunner

from hatchlot.cli.output import (
    Format,
    confirm_or_abort,
    count_line,
    echo,
    echo_pairs,
    parse_format,
    render,
)
from hatchlot.errors import ValidationError
from hatchlot.quantities.base import Quantity

HEADINGS = ["lot", "fish", "weight"]
ROWS = [["2024-CHK-01", Decimal(50000), Quantity("2.5", "g")]]


def test_the_three_formats_parse_and_two_of_them_are_for_machines():
    assert parse_format("table") is Format.TABLE
    assert Format.CSV.is_machine
    assert Format.PLAIN.is_machine
    assert not Format.TABLE.is_machine
    with pytest.raises(ValidationError):
        parse_format("yaml")


def test_the_table_form_has_headings_and_a_rule():
    text = render(HEADINGS, ROWS, Format.TABLE)
    lines = text.splitlines()
    assert lines[0].startswith("lot")
    assert set(lines[1]) <= {"-", " "}


def test_the_csv_form_splits_a_quantity_into_two_columns():
    text = render(HEADINGS, ROWS, Format.CSV)
    assert text.splitlines()[0] == "lot,fish,weight,weight_unit"


def test_the_plain_form_has_no_headings_and_no_units():
    text = render(HEADINGS, ROWS, Format.PLAIN)
    assert text == "2024-CHK-01\t50000\t2.5"


def test_numbers_go_right_in_a_table_and_text_goes_left():
    text = render(["name", "count"], [["a", Decimal(1)]], Format.TABLE)
    assert text.splitlines()[2].startswith("a")


def test_a_listing_with_no_headings_is_refused():
    with pytest.raises(ValidationError):
        render([], [], Format.TABLE)


def test_an_empty_listing_still_has_a_heading_in_the_table_form():
    assert len(render(HEADINGS, [], Format.TABLE).splitlines()) == 2
    assert render(HEADINGS, [], Format.PLAIN) == ""


def test_echoing_nothing_prints_nothing():
    runner = CliRunner()

    @click.command()
    def show() -> None:
        echo(HEADINGS, [], Format.PLAIN)

    assert runner.invoke(show).output == ""


def test_echoing_a_listing_prints_it():
    runner = CliRunner()

    @click.command()
    def show() -> None:
        echo(HEADINGS, ROWS, Format.PLAIN)

    assert "2024-CHK-01" in runner.invoke(show).output


def test_a_pair_block_prints_as_labels_or_as_a_row():
    runner = CliRunner()

    @click.command()
    @click.argument("form")
    def show(form: str) -> None:
        echo_pairs([("station", "Cold Creek"), ("lots", Decimal(3))], parse_format(form))

    assert "station" in runner.invoke(show, ["table"]).output
    assert runner.invoke(show, ["csv"]).output.splitlines()[0] == "station,lots"


def test_a_pair_block_of_nothing_is_refused():
    with pytest.raises(ValidationError):
        echo_pairs([], Format.TABLE)


def test_a_confirmation_can_be_skipped_and_can_abort():
    confirm_or_abort("go ahead?", yes=True)
    runner = CliRunner()

    @click.command()
    def risky() -> None:
        confirm_or_abort("really?", yes=False)
        click.echo("done")

    assert runner.invoke(risky, input="n\n").exit_code != 0
    assert "done" in runner.invoke(risky, input="y\n").output


def test_the_plural_of_a_noun():
    assert count_line("lot", 1) == "1 lot"
    assert count_line("lot", 0) == "0 lots"
    assert count_line("lot", 3) == "3 lots"


def test_booleans_and_nothing_print_in_every_form():
    text = render(["a", "b"], [[True, None]], Format.PLAIN)
    assert text == "true\t"
    assert "yes" in render(["a", "b"], [[True, None]], Format.TABLE)
