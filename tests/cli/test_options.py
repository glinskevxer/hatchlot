import click
import pytest
from click.testing import CliRunner

from hatchlot.calendar import DateRange
from hatchlot.cli.options import (
    entered_by_option,
    format_option,
    window_from,
    window_options,
)


def test_the_format_option_defaults_to_the_table():
    @click.command()
    @format_option
    def show(form: str) -> None:
        click.echo(form)

    assert CliRunner().invoke(show).output.strip() == "table"
    assert CliRunner().invoke(show, ["--format", "csv"]).output.strip() == "csv"


def test_the_format_option_refuses_a_form_it_does_not_know():
    @click.command()
    @format_option
    def show(form: str) -> None:
        click.echo(form)

    assert CliRunner().invoke(show, ["--format", "yaml"]).exit_code != 0


def test_the_window_options_are_optional_by_default():
    @click.command()
    @window_options()
    def show(start: str, end: str) -> None:
        click.echo(f"{start}|{end}")

    assert CliRunner().invoke(show).output.strip() == "|"
    result = CliRunner().invoke(show, ["--from", "2025-03-01", "--to", "2025-03-31"])
    assert result.output.strip() == "2025-03-01|2025-03-31"


def test_the_window_options_can_be_required():
    @click.command()
    @window_options(required=True)
    def show(start: str, end: str) -> None:
        click.echo(f"{start}|{end}")

    assert CliRunner().invoke(show).exit_code != 0


def test_the_entered_by_option_has_a_default():
    @click.command()
    @entered_by_option
    def show(entered_by: str) -> None:
        click.echo(entered_by)

    assert CliRunner().invoke(show).output.strip() == "hatchery"
    assert CliRunner().invoke(show, ["--by", "kt"]).output.strip() == "kt"


def test_a_window_of_both_days_becomes_a_range():
    assert window_from("2025-03-01", "2025-03-31") == DateRange("2025-03-01", "2025-03-31")


def test_a_window_of_neither_day_is_nothing():
    assert window_from("", "") is None


def test_half_a_window_is_a_usage_error():
    with pytest.raises(click.UsageError):
        window_from("2025-03-01", "")
    with pytest.raises(click.UsageError):
        window_from("", "2025-03-31")
