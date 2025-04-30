"""Not importing the same file twice, and not importing the same row twice.

Both happen and they need different answers. A whole file gets sent again
because somebody was not sure it went through, and the right answer is to notice
and do nothing. Individual rows repeat because a datalogger's export overlaps
the last one, and the right answer there is to take the new rows and leave the
ones already held.

Content hashing does both. The file hash is over the bytes, so a file that is
byte identical is the same file. The row hash is over the values that identify a
row rather than the whole row, because a datalogger will happily re-export the
same reading with a different number of trailing zeroes on it.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from ..errors import ValidationError
from ..quantities.base import Quantity


def file_hash(text: str) -> str:
    """A hash over the whole file, for spotting an exact resend."""

    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _canonical(value: Any) -> str:
    """One printed form per value, whatever shape it arrived in."""

    if isinstance(value, Quantity):
        return f"{value.to(value.symbol).amount.normalize():f}{value.symbol}"
    if isinstance(value, Decimal):
        return f"{value.normalize():f}"
    if isinstance(value, datetime):
        return value.isoformat(timespec="seconds")
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, str):
        return value.strip().casefold()
    return str(value)


def row_key(row: dict[str, Any], keys: tuple[str, ...]) -> str:
    """A hash over the fields that identify a row."""

    if not keys:
        raise ValidationError("a row key needs fields in it", field="keys")
    missing = [key for key in keys if key not in row]
    if missing:
        raise ValidationError(f"the row has no {missing[0]}", field="keys")
    parts = [f"{key}={_canonical(row[key])}" for key in keys]
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()


@dataclass
class ImportLedger:
    """What has already been imported, so it is not imported again."""

    files: set[str] = field(default_factory=set)
    rows: set[str] = field(default_factory=set)

    def seen_file(self, text: str) -> bool:
        return file_hash(text) in self.files

    def record_file(self, text: str) -> str:
        digest = file_hash(text)
        self.files.add(digest)
        return digest

    def seen_row(self, row: dict[str, Any], keys: tuple[str, ...]) -> bool:
        return row_key(row, keys) in self.rows

    def record_row(self, row: dict[str, Any], keys: tuple[str, ...]) -> str:
        digest = row_key(row, keys)
        self.rows.add(digest)
        return digest

    def __len__(self) -> int:
        return len(self.rows)

    @property
    def file_count(self) -> int:
        return len(self.files)


@dataclass(frozen=True, slots=True)
class DedupeResult:
    """What survived the deduplication."""

    fresh: tuple[dict[str, Any], ...]
    duplicates: tuple[dict[str, Any], ...]
    within_file: int

    @property
    def kept(self) -> int:
        return len(self.fresh)

    @property
    def is_all_new(self) -> bool:
        return not self.duplicates and self.within_file == 0


def dedupe(rows: list[dict[str, Any]], keys: tuple[str, ...], ledger: ImportLedger) -> DedupeResult:
    """Drop rows already held, and rows repeated inside the file itself.

    A row repeated inside one file is counted separately from one already in the
    ledger, because the two mean different things: the first is a vendor problem
    and the second is normal.
    """

    fresh: list[dict[str, Any]] = []
    duplicates: list[dict[str, Any]] = []
    inside: set[str] = set()
    repeats = 0
    for row in rows:
        digest = row_key(row, keys)
        if digest in ledger.rows:
            duplicates.append(row)
            continue
        if digest in inside:
            repeats += 1
            continue
        inside.add(digest)
        fresh.append(row)
    return DedupeResult(fresh=tuple(fresh), duplicates=tuple(duplicates), within_file=repeats)


def commit_rows(result: DedupeResult, keys: tuple[str, ...], ledger: ImportLedger) -> int:
    """Put the fresh rows into the ledger so the next import skips them."""

    for row in result.fresh:
        ledger.record_row(row, keys)
    return len(result.fresh)


def overlap_share(result: DedupeResult) -> Decimal:
    """How much of a file was already held, which says how the export is set up."""

    total = len(result.fresh) + len(result.duplicates) + result.within_file
    if total == 0:
        return Decimal(0)
    return Decimal(len(result.duplicates)) / Decimal(total)
