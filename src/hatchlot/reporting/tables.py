"""Plain text tables, because that is what gets printed and pasted into email.

No dependency, no colour, no box drawing characters that turn into question
marks in somebody's terminal. Columns are sized to their content, numbers go
right, text goes left, and a value too wide for its column widens the column
rather than being cut off. A report that silently truncates a fish count is
worse than a wide report.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
from typing import Any

from ..errors import ValidationError
from ..numeric import quantize
from ..quantities.base import Quantity


class Align(Enum):
    """Which way a column lines up."""

    LEFT = "left"
    RIGHT = "right"

    @property
    def is_right(self) -> bool:
        return self is Align.RIGHT


@dataclass(frozen=True, slots=True)
class Column:
    """One column: its heading, how it lines up, and how it prints."""

    heading: str
    align: Align = Align.LEFT
    places: int | None = None

    def __post_init__(self) -> None:
        if not self.heading.strip():
            raise ValidationError("a column needs a heading", field="heading")
        object.__setattr__(self, "heading", self.heading.strip())
        if not isinstance(self.align, Align):
            raise ValidationError(f"{self.align!r} is not an alignment", field="align")
        if self.places is not None and self.places < 0:
            raise ValidationError("places cannot be negative", field="places")

    def render(self, value: Any) -> str:
        """One cell, printed the way this column prints things."""

        if value is None:
            return ""
        if isinstance(value, Quantity):
            amount = (
                quantize(value.amount, self.places) if self.places is not None else value.amount
            )
            return f"{amount.normalize():f} {value.symbol}"
        if isinstance(value, Decimal):
            if self.places is not None:
                return f"{quantize(value, self.places):f}"
            return f"{value.normalize():f}"
        if isinstance(value, bool):
            return "yes" if value else "no"
        return str(value)


def render_table(columns: list[Column], rows: list[list[Any]]) -> str:
    """Render a table, sized to what is in it."""

    if not columns:
        raise ValidationError("a table needs columns", field="columns")
    for index, row in enumerate(rows):
        if len(row) != len(columns):
            raise ValidationError(
                f"row {index + 1} has {len(row)} cells against {len(columns)} columns",
                field="rows",
            )
    cells = [
        [column.render(value) for column, value in zip(columns, row, strict=True)] for row in rows
    ]
    widths = [
        max([len(column.heading), *[len(row[index]) for row in cells]])
        for index, column in enumerate(columns)
    ]
    lines = [
        "  ".join(
            column.heading.rjust(widths[index])
            if column.align.is_right
            else column.heading.ljust(widths[index])
            for index, column in enumerate(columns)
        ).rstrip(),
        "  ".join("-" * width for width in widths).rstrip(),
    ]
    for row in cells:
        lines.append(
            "  ".join(
                value.rjust(widths[index])
                if columns[index].align.is_right
                else value.ljust(widths[index])
                for index, value in enumerate(row)
            ).rstrip()
        )
    return "\n".join(lines)


def render_pairs(pairs: list[tuple[str, Any]], *, places: int | None = None) -> str:
    """A two column block of label and value, for the head of a report."""

    if not pairs:
        raise ValidationError("nothing to render", field="pairs")
    column = Column(heading="value", places=places)
    width = max(len(label) for label, _ in pairs)
    return "\n".join(
        f"{label.ljust(width)}  {column.render(value)}".rstrip() for label, value in pairs
    )


def heading(text: str, *, underline: str = "=") -> str:
    """A heading with a rule under it."""

    if not text.strip():
        raise ValidationError("a heading needs words", field="text")
    if len(underline) != 1:
        raise ValidationError("an underline is one character", field="underline")
    cleaned = text.strip()
    return f"{cleaned}\n{underline * len(cleaned)}"


def bullet_list(items: list[str], *, marker: str = "-") -> str:
    """A list of lines, for the exceptions at the end of a report."""

    if not items:
        return ""
    return "\n".join(f"{marker} {item}" for item in items)


def join_sections(sections: list[str]) -> str:
    """Put a report together, dropping the sections that came back empty."""

    return "\n\n".join(section.strip() for section in sections if section.strip())
