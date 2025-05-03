"""One import, end to end, with a report at the end of it.

Reading, deduplicating and recording are three modules and one operation. This
runs them in order and hands back a report, because the person who imported a
file wants one answer and not three: how many rows went in, how many were
already held, how many would not read, and whether that is worth looking at.

Nothing is written to the ledger until the read has finished, so a file that
falls over halfway leaves nothing behind.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from ..errors import ValidationError
from ..numeric import Number, to_decimal
from .dedupe import DedupeResult, ImportLedger, commit_rows, dedupe, file_hash
from .profile import Profile, choose_profile
from .reader import ReadResult, read_rows


@dataclass(frozen=True, slots=True)
class ImportReport:
    """What one import did."""

    profile: str
    digest: str
    read: ReadResult
    deduped: DedupeResult | None
    imported: int
    skipped_as_seen_file: bool

    @property
    def rejected(self) -> int:
        return len(self.read.rejected)

    @property
    def duplicates(self) -> int:
        return len(self.deduped.duplicates) if self.deduped else 0

    @property
    def is_clean(self) -> bool:
        return self.rejected == 0 and not self.skipped_as_seen_file

    def line(self) -> str:
        if self.skipped_as_seen_file:
            return f"{self.profile}: already imported, nothing done"
        return (
            f"{self.profile}: {self.imported} rows in, {self.duplicates} already held, "
            f"{self.rejected} rejected"
        )


def run_import(
    profile: Profile,
    text: str,
    ledger: ImportLedger,
    keys: tuple[str, ...],
    *,
    reject_ceiling: Number = "0.2",
) -> ImportReport:
    """Read a file, drop what is already held, and record what is left.

    A file over the rejection ceiling is refused rather than partly imported,
    because a file that is a fifth unreadable is usually the wrong file rather
    than a file with problems in it.
    """

    ceiling = to_decimal(reject_ceiling, field="reject_ceiling")
    if not 0 <= ceiling <= 1:
        raise ValidationError("a rejection ceiling is a share", field="reject_ceiling")
    digest = file_hash(text)
    if digest in ledger.files:
        return ImportReport(
            profile=profile.code,
            digest=digest,
            read=ReadResult(profile=profile.code, rows=(), rejected=()),
            deduped=None,
            imported=0,
            skipped_as_seen_file=True,
        )
    result = read_rows(profile, text)
    total = result.read + len(result.rejected)
    if total and Decimal(len(result.rejected)) / Decimal(total) > ceiling:
        raise ValidationError(
            f"{len(result.rejected)} of {total} rows would not read", field="text"
        )
    deduped = dedupe(list(result.rows), keys, ledger)
    imported = commit_rows(deduped, keys, ledger)
    ledger.record_file(text)
    return ImportReport(
        profile=profile.code,
        digest=digest,
        read=result,
        deduped=deduped,
        imported=imported,
        skipped_as_seen_file=False,
    )


def run_with_profiles(
    profiles: list[Profile],
    text: str,
    ledger: ImportLedger,
    keys: tuple[str, ...],
) -> ImportReport:
    """Pick the profile off the file's own header, then import it."""

    header = text.splitlines()
    if not header:
        raise ValidationError("the file has nothing in it", field="text")
    chosen = choose_profile(profiles, header[0].split(","))
    return run_import(chosen, text, ledger, keys)


def rows_of(report: ImportReport) -> tuple[dict[str, Any], ...]:
    """The rows an import actually took in."""

    return report.deduped.fresh if report.deduped else ()


def import_rate(report: ImportReport) -> Decimal:
    """The share of a file's rows that ended up imported."""

    total = report.read.read + len(report.read.rejected)
    if total == 0:
        return Decimal(0)
    return Decimal(report.imported) / Decimal(total)
