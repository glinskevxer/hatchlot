"""Column mapping profiles, because every vendor writes a different file.

The datalogger exports `DateTime,Temp_F`. The scale writes `date,net_wt_lb`. The
feed mill sends a spreadsheet with the columns in a different order every month.
None of that is worth changing the engine for, so a profile says which column
means what and which unit it is in, and the reader does the rest.

A profile is data rather than code on purpose. Adding a vendor should not be a
release.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum
from typing import Any

from ..errors import ValidationError
from ..identifiers import normalise_code
from ..numeric import Number, to_decimal
from ..units import Dimension, convert, unit


class FieldKind(Enum):
    """What a column becomes once it is read."""

    TEXT = "text"
    NUMBER = "number"
    DATE = "date"
    TIMESTAMP = "timestamp"
    QUANTITY = "quantity"

    @property
    def needs_unit(self) -> bool:
        return self is FieldKind.QUANTITY


@dataclass(frozen=True, slots=True)
class ColumnMap:
    """One column in the file, and what it means here."""

    column: str
    name: str
    kind: FieldKind
    source_unit: str = ""
    target_unit: str = ""
    required: bool = True

    def __post_init__(self) -> None:
        if not self.column.strip():
            raise ValidationError("a column mapping needs a column", field="column")
        object.__setattr__(self, "column", self.column.strip())
        if not self.name.strip():
            raise ValidationError("a column mapping needs a name", field="name")
        object.__setattr__(self, "name", self.name.strip())
        if not isinstance(self.kind, FieldKind):
            raise ValidationError(f"{self.kind!r} is not a field kind", field="kind")
        if self.kind.needs_unit:
            if not self.source_unit or not self.target_unit:
                raise ValidationError(
                    "a quantity column needs a source and a target unit", field="source_unit"
                )
            source = unit(self.source_unit)
            target = unit(self.target_unit)
            if source.dimension is not target.dimension:
                raise ValidationError(
                    f"{self.source_unit} and {self.target_unit} measure different things",
                    field="target_unit",
                )
        elif self.source_unit or self.target_unit:
            raise ValidationError(f"a {self.kind.value} column takes no units", field="source_unit")

    @property
    def dimension(self) -> Dimension | None:
        return unit(self.source_unit).dimension if self.kind.needs_unit else None

    def convert(self, value: Number) -> Decimal:
        """Bring a raw number into the unit the station keeps."""

        if not self.kind.needs_unit:
            return to_decimal(value, field=self.name)
        return convert(value, self.source_unit, self.target_unit)


@dataclass
class Profile:
    """One vendor's file layout."""

    code: str
    description: str
    columns: list[ColumnMap] = field(default_factory=list)
    delimiter: str = ","
    skip_rows: int = 0

    def __post_init__(self) -> None:
        self.code = normalise_code(self.code, field="profile")
        if not self.description.strip():
            raise ValidationError("a profile needs a description", field="description")
        self.description = self.description.strip()
        if len(self.delimiter) != 1:
            raise ValidationError("a delimiter is one character", field="delimiter")
        if self.skip_rows < 0:
            raise ValidationError("cannot skip a negative number of rows", field="skip_rows")
        names = [column.name for column in self.columns]
        if len(set(names)) != len(names):
            raise ValidationError("two columns map to one name", field="columns")

    def add(self, column: ColumnMap) -> ColumnMap:
        if any(existing.name == column.name for existing in self.columns):
            raise ValidationError(f"{column.name} is already mapped", field="columns")
        if any(existing.column == column.column for existing in self.columns):
            raise ValidationError(f"{column.column} is already used", field="columns")
        self.columns.append(column)
        return column

    def by_name(self, name: str) -> ColumnMap:
        for column in self.columns:
            if column.name == name:
                return column
        raise ValidationError(f"{name!r} is not in this profile", field="name")

    def required_columns(self) -> tuple[str, ...]:
        return tuple(column.column for column in self.columns if column.required)

    def missing_from(self, header: list[str]) -> tuple[str, ...]:
        """Which required columns a file's header does not have."""

        present = {name.strip() for name in header}
        return tuple(column for column in self.required_columns() if column not in present)

    def matches(self, header: list[str]) -> bool:
        return not self.missing_from(header)

    def names(self) -> tuple[str, ...]:
        return tuple(column.name for column in self.columns)


def choose_profile(profiles: list[Profile], header: list[str]) -> Profile:
    """Pick the profile that fits a file, refusing an ambiguous answer.

    Two profiles that both fit is not a tie to be broken by order. It means the
    profiles are not specific enough, and quietly picking one is how a scale file
    gets read as a datalogger file for six months.
    """

    fitting = [profile for profile in profiles if profile.matches(header)]
    if not fitting:
        raise ValidationError("no profile fits that file", field="header")
    if len(fitting) > 1:
        names = ", ".join(sorted(profile.code for profile in fitting))
        raise ValidationError(f"more than one profile fits: {names}", field="header")
    return fitting[0]


def describe_row(profile: Profile, row: dict[str, Any]) -> dict[str, Any]:
    """Rename a raw row's keys to the station's names, without converting."""

    out: dict[str, Any] = {}
    for column in profile.columns:
        if column.column in row:
            out[column.name] = row[column.column]
    return out
