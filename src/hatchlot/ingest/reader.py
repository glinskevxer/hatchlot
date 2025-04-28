"""Reading a file through a profile, and keeping the rows that will not read.

The rule here is that a bad row never stops an import and never disappears.
Every row that fails conversion goes into a quarantine list with the reason and
the line number, and the import carries on. A hatchery file is a thousand rows
off a datalogger with three bad ones in it, and an importer that refuses the
whole file over those three gets run once and then worked around.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from decimal import Decimal
from io import StringIO
from typing import Any

from ..calendar import parse_date, parse_timestamp
from ..errors import ValidationError
from ..quantities.base import Quantity
from .profile import FieldKind, Profile


@dataclass(frozen=True, slots=True)
class Rejected:
    """One row that would not read, kept with the reason."""

    line: int
    reason: str
    raw: dict[str, str]

    @property
    def summary(self) -> str:
        return f"line {self.line}: {self.reason}"


@dataclass(frozen=True, slots=True)
class ReadResult:
    """Everything an import produced, good and bad."""

    profile: str
    rows: tuple[dict[str, Any], ...]
    rejected: tuple[Rejected, ...]

    @property
    def read(self) -> int:
        return len(self.rows)

    @property
    def is_clean(self) -> bool:
        return not self.rejected

    @property
    def acceptance(self) -> Decimal:
        total = len(self.rows) + len(self.rejected)
        if total == 0:
            return Decimal(0)
        return Decimal(len(self.rows)) / Decimal(total)

    def column(self, name: str) -> tuple[Any, ...]:
        return tuple(row[name] for row in self.rows if name in row)


def _convert_cell(column_kind: FieldKind, raw: str, mapping: Any) -> Any:
    text = raw.strip()
    if column_kind is FieldKind.TEXT:
        return text
    if column_kind is FieldKind.DATE:
        return parse_date(text, field=mapping.name)
    if column_kind is FieldKind.TIMESTAMP:
        return parse_timestamp(text, field=mapping.name)
    if column_kind is FieldKind.NUMBER:
        return mapping.convert(text)
    return Quantity(mapping.convert(text), mapping.target_unit)


def read_rows(profile: Profile, text: str) -> ReadResult:
    """Read a file's text through a profile."""

    lines = text.splitlines()
    if profile.skip_rows:
        lines = lines[profile.skip_rows :]
    if not lines:
        raise ValidationError("the file has nothing in it", field="text")
    reader = csv.DictReader(StringIO("\n".join(lines)), delimiter=profile.delimiter)
    header = list(reader.fieldnames or [])
    missing = profile.missing_from(header)
    if missing:
        raise ValidationError(f"the file is missing {', '.join(missing)}", field="header")
    rows: list[dict[str, Any]] = []
    rejected: list[Rejected] = []
    for offset, raw in enumerate(reader, start=2 + profile.skip_rows):
        cleaned: dict[str, Any] = {}
        problem: str | None = None
        for mapping in profile.columns:
            value = raw.get(mapping.column)
            if value is None or not str(value).strip():
                if mapping.required:
                    problem = f"{mapping.column} is empty"
                    break
                continue
            try:
                cleaned[mapping.name] = _convert_cell(mapping.kind, str(value), mapping)
            except ValidationError as error:
                # Named for the column the station knows, not the unit that
                # happened to be on the failing conversion.
                problem = f"{mapping.name}: {error}"
                break
        if problem is None:
            rows.append(cleaned)
        else:
            rejected.append(
                Rejected(
                    line=offset,
                    reason=problem,
                    raw={key: str(value) for key, value in raw.items() if key},
                )
            )
    return ReadResult(profile=profile.code, rows=tuple(rows), rejected=tuple(rejected))


def read_file(profile: Profile, path: str) -> ReadResult:
    """Read a file off disk through a profile."""

    try:
        with open(path, encoding="utf-8") as handle:
            return read_rows(profile, handle.read())
    except FileNotFoundError:
        raise ValidationError(f"no file at {path}", field="path") from None
    except UnicodeDecodeError:
        raise ValidationError(f"{path} is not text this reader can read", field="path") from None


def rejected_summary(result: ReadResult, *, limit: int = 5) -> tuple[str, ...]:
    """The first few rejections, for a message somebody has to read."""

    if limit < 1:
        raise ValidationError("a summary shows at least one line", field="limit")
    return tuple(entry.summary for entry in result.rejected[:limit])
