"""Exporting a table, for the half of the world that wants a spreadsheet.

Two rules. Numbers go out unrounded and unformatted, because a spreadsheet will
do its own rounding and a pre-rounded number cannot be un-rounded. And a
quantity goes out as two columns, the amount and the unit, because a cell
containing `2.5 g` is text and will not add up.
"""

from __future__ import annotations

import csv
from decimal import Decimal
from io import StringIO
from typing import Any

from ..errors import ValidationError
from ..quantities.base import Quantity
from ..quantities.temperature import Temperature


def _cells(value: Any, name: str) -> list[tuple[str, str]]:
    """One value as one or two columns of text."""

    if isinstance(value, Quantity):
        return [(name, str(value.amount)), (f"{name}_unit", value.symbol)]
    if isinstance(value, Temperature):
        return [(name, str(value.value)), (f"{name}_scale", value.scale)]
    if isinstance(value, Decimal):
        return [(name, str(value))]
    if value is None:
        return [(name, "")]
    if isinstance(value, bool):
        return [(name, "true" if value else "false")]
    return [(name, str(value))]


def to_csv(headings: list[str], rows: list[list[Any]]) -> str:
    """Render rows as CSV, splitting quantities into value and unit columns."""

    if not headings:
        raise ValidationError("an export needs headings", field="headings")
    if len(set(headings)) != len(headings):
        raise ValidationError("two columns share a heading", field="headings")
    for index, row in enumerate(rows):
        if len(row) != len(headings):
            raise ValidationError(
                f"row {index + 1} has {len(row)} cells against {len(headings)} headings",
                field="rows",
            )
    expanded: list[list[tuple[str, str]]] = [
        [cell for name, value in zip(headings, row, strict=True) for cell in _cells(value, name)]
        for row in rows
    ]
    if expanded:
        header = [name for name, _ in expanded[0]]
        for row in expanded[1:]:
            if [name for name, _ in row] != header:
                raise ValidationError("the rows do not all have the same shape", field="rows")
    else:
        header = list(headings)
    buffer = StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(header)
    for row in expanded:
        writer.writerow([value for _, value in row])
    return buffer.getvalue()


def write_csv(path: str, headings: list[str], rows: list[list[Any]]) -> int:
    """Write an export to a file and say how many rows went in it."""

    text = to_csv(headings, rows)
    try:
        with open(path, "w", encoding="utf-8", newline="") as handle:
            handle.write(text)
    except (IsADirectoryError, FileNotFoundError, PermissionError) as error:
        raise ValidationError(f"cannot write to {path}: {error}", field="path") from None
    return len(rows)


def to_records(headings: list[str], rows: list[list[Any]]) -> tuple[dict[str, str], ...]:
    """The same expansion as a list of dictionaries, for a caller that wants one."""

    text = to_csv(headings, rows)
    reader = csv.DictReader(StringIO(text))
    return tuple({key: value for key, value in row.items() if key} for row in reader)
