"""The movement ledger, which is the only honest account of a population.

A lot carries a population number and that number is a running total somebody
has been editing for a year. The ledger is the other version: every event that
ever changed the count, in order, so the number can be rebuilt from nothing.

When the two disagree, the ledger is right and the difference is an adjustment
that has to be entered by a person with a reason. That rule is the entire point.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from enum import Enum

from ..calendar import DateRange, parse_date
from ..errors import ValidationError
from ..identifiers import normalise_code
from ..journal import Journal
from ..numeric import Number, require_positive, safe_divide


class EntryKind(Enum):
    """What happened, and which way it moves the count."""

    PONDED = "ponded"
    TRANSFER_IN = "transfer_in"
    TRANSFER_OUT = "transfer_out"
    MORTALITY = "mortality"
    SAMPLE = "sample"
    RELEASE = "release"
    ADJUSTMENT = "adjustment"

    @property
    def sign(self) -> int:
        """Plus one if it adds fish, minus one if it takes them away."""

        if self in {EntryKind.PONDED, EntryKind.TRANSFER_IN}:
            return 1
        if self is EntryKind.ADJUSTMENT:
            return 0
        return -1

    @property
    def needs_a_reason(self) -> bool:
        return self in {EntryKind.ADJUSTMENT, EntryKind.MORTALITY}


@dataclass(frozen=True, slots=True)
class LedgerEntry:
    """One event against one lot."""

    day: date
    lot: str
    kind: EntryKind
    count: Decimal
    entered_by: str
    reason: str = ""
    counterparty: str = ""

    def __init__(
        self,
        day: object,
        lot: str,
        kind: EntryKind,
        count: Number,
        entered_by: str,
        reason: str = "",
        counterparty: str = "",
    ) -> None:
        object.__setattr__(self, "day", parse_date(day))
        object.__setattr__(self, "lot", normalise_code(lot, field="lot"))
        if not isinstance(kind, EntryKind):
            raise ValidationError(f"{kind!r} is not a ledger entry kind", field="kind")
        object.__setattr__(self, "kind", kind)
        object.__setattr__(self, "count", require_positive(count, field="count"))
        if not entered_by.strip():
            raise ValidationError("a ledger entry needs whoever made it", field="entered_by")
        object.__setattr__(self, "entered_by", entered_by.strip())
        if kind.needs_a_reason and not reason.strip():
            raise ValidationError(f"a {kind.value} needs a reason", field="reason")
        object.__setattr__(self, "reason", reason.strip())
        object.__setattr__(
            self,
            "counterparty",
            normalise_code(counterparty, field="counterparty") if counterparty else "",
        )

    @property
    def effect(self) -> Decimal:
        """What this entry does to the running count."""

        return self.count * Decimal(self.kind.sign)


@dataclass(frozen=True, slots=True)
class LedgerBalance:
    """A lot rebuilt from its own history."""

    lot: str
    opened: Decimal
    added: Decimal
    removed: Decimal
    adjusted: Decimal
    closing: Decimal

    @property
    def loss_share(self) -> Decimal:
        base = self.opened + self.added
        if base == 0:
            return Decimal(0)
        return safe_divide(self.removed, base, field="opened")


class Ledger:
    """Every entry, over every lot."""

    def __init__(self) -> None:
        self._journal: Journal[LedgerEntry] = Journal(
            day_of=lambda entry: entry.day, key_of=lambda entry: entry.lot
        )

    def record(self, entry: LedgerEntry) -> LedgerEntry:
        return self._journal.record(entry)

    def __len__(self) -> int:
        return len(self._journal)

    def lots(self) -> tuple[str, ...]:
        return self._journal.keys()

    def for_lot(self, lot: str) -> tuple[LedgerEntry, ...]:
        return self._journal.for_key(lot)

    def within(self, window: DateRange) -> tuple[LedgerEntry, ...]:
        return self._journal.within(window)

    def of_kind(self, kind: EntryKind) -> tuple[LedgerEntry, ...]:
        return tuple(entry for entry in self._journal.all() if entry.kind is kind)

    def balance(self, lot: str, *, as_of: object | None = None) -> LedgerBalance:
        """Rebuild a lot's population from the entries, up to a day."""

        entries = self.for_lot(lot)
        if as_of is not None:
            cutoff = parse_date(as_of)
            entries = tuple(entry for entry in entries if entry.day <= cutoff)
        opened = Decimal(0)
        added = Decimal(0)
        removed = Decimal(0)
        adjusted = Decimal(0)
        running = Decimal(0)
        for entry in entries:
            if entry.kind is EntryKind.PONDED:
                opened += entry.count
                running += entry.count
            elif entry.kind is EntryKind.ADJUSTMENT:
                target = entry.count
                adjusted += target - running
                running = target
            elif entry.kind.sign > 0:
                added += entry.count
                running += entry.count
            else:
                if entry.count > running:
                    raise ValidationError(
                        f"{entry.kind.value} of {entry.count} on {entry.day} takes "
                        f"{normalise_code(lot)} below zero",
                        field="count",
                    )
                removed += entry.count
                running -= entry.count
        return LedgerBalance(
            lot=normalise_code(lot, field="lot"),
            opened=opened,
            added=added,
            removed=removed,
            adjusted=adjusted,
            closing=running,
        )

    def mortality(self, lot: str) -> Decimal:
        return sum(
            (entry.count for entry in self.for_lot(lot) if entry.kind is EntryKind.MORTALITY),
            Decimal(0),
        )

    def check_against(self, lot: str, carried: Number) -> Decimal:
        """The difference between a carried population and the ledger."""

        return require_positive(carried, field="carried") - self.balance(lot).closing


def adjust_to(
    ledger: Ledger, lot: str, day: object, carried: Number, entered_by: str, reason: str
) -> LedgerEntry | None:
    """Put an adjustment on the ledger so it agrees with a counted population.

    None means they already agreed, which is worth knowing and worth not
    writing an entry about.
    """

    difference = ledger.check_against(lot, carried)
    if difference == 0:
        return None
    return ledger.record(
        LedgerEntry(
            day=day,
            lot=lot,
            kind=EntryKind.ADJUSTMENT,
            count=carried,
            entered_by=entered_by,
            reason=reason,
        )
    )
