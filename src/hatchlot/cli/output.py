"""How the commands print, and the one switch that changes it.

Every command that lists something takes the same `--format` and prints through
here, so a station can pipe any listing into a spreadsheet without every command
having grown its own idea of what CSV means. The table form is for people, the
csv form is for spreadsheets, and the plain form is for the shell: one value per
line, no headings, nothing to strip.
"""

from __future__ import annotations

from decimal import Decimal
from enum import Enum
from typing import Any

import click

from ..errors import ValidationError
from ..quantities.base import Quantity
from ..reporting.export import to_csv
from ..reporting.tables import Align, Column, render_table


class Format(Enum):
    """How a listing comes out."""

    TABLE = "table"
    CSV = "csv"
    PLAIN = "plain"

    @property
    def is_machine(self) -> bool:
        return self is not Format.TABLE


FORMAT_CHOICE = click.Choice([entry.value for entry in Format])


def parse_format(value: str) -> Format:
    try:
        return Format(value)
    except ValueError:
        raise ValidationError(f"{value!r} is not an output format", field="format") from None


def _column(heading: str, sample: Any, places: int) -> Column:
    right = isinstance(sample, Decimal | Quantity | int) and not isinstance(sample, bool)
    return Column(
        heading=heading,
        align=Align.RIGHT if right else Align.LEFT,
        places=places if right else None,
    )


def render(headings: list[str], rows: list[list[Any]], form: Format, *, places: int = 2) -> str:
    """Render a listing in whichever form was asked for."""

    if not headings:
        raise ValidationError("a listing needs headings", field="headings")
    if form is Format.CSV:
        return to_csv(headings, rows).rstrip("\n")
    if form is Format.PLAIN:
        return "\n".join("\t".join(_plain(value) for value in row) for row in rows)
    sample = rows[0] if rows else [None] * len(headings)
    columns = [_column(heading, sample[index], places) for index, heading in enumerate(headings)]
    return render_table(columns, rows)


def _plain(value: Any) -> str:
    if isinstance(value, Quantity):
        return f"{value.amount.normalize():f}"
    if isinstance(value, Decimal):
        return f"{value.normalize():f}"
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def echo(headings: list[str], rows: list[list[Any]], form: Format, *, places: int = 2) -> None:
    """Print a listing, and say nothing at all when there is nothing in it."""

    text = render(headings, rows, form, places=places)
    if text:
        click.echo(text)


def echo_pairs(pairs: list[tuple[str, Any]], form: Format, *, places: int = 2) -> None:
    """Print a summary block, or its machine readable form."""

    if not pairs:
        raise ValidationError("nothing to print", field="pairs")
    if form.is_machine:
        echo(
            [label for label, _ in pairs],
            [[value for _, value in pairs]],
            form,
            places=places,
        )
        return
    from ..reporting.tables import render_pairs

    click.echo(render_pairs(pairs, places=places))


def confirm_or_abort(message: str, *, yes: bool) -> None:
    """Ask before something that cannot be undone, unless told not to."""

    if yes:
        return
    if not click.confirm(message, default=False):
        raise click.Abort


def count_line(noun: str, number: int) -> str:
    """`1 lot` or `3 lots`, which is the one place plurals are decided."""

    if number == 1:
        return f"1 {noun}"
    return f"{number} {noun}s"
