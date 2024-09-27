"""Moving rearing fish: between units, out of a lot, and back into one.

Three operations and one rule. Every one of them writes both sides to the
ledger, so the ledger can still rebuild each lot on its own afterwards. A
transfer that only wrote the leaving side would balance the station and lose a
raceway, which is exactly the kind of error that survives a year.

Merging is the awkward one. Two lots become one and the mean weight of the
result is the weighted mean, but the identity of the smaller lot is gone. So the
merged lot keeps the larger lot's code and the smaller one is closed with a note
pointing at where its fish went.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from ..calendar import parse_date
from ..errors import PolicyError, StateError, ValidationError
from ..identifiers import LotCode, split_suffix
from ..numeric import Number, require_positive
from ..quantities.base import Quantity
from .container import Container
from .ledger import EntryKind, Ledger, LedgerEntry
from .lot import LotState, RearingLot


@dataclass(frozen=True, slots=True)
class Transfer:
    """One movement of fish between two places."""

    day: date
    lot: str
    fish: Decimal
    origin: str
    destination: str
    moved_by: str


def _check_movable(lot: RearingLot) -> None:
    if lot.state.is_closed:
        raise StateError(f"lot {lot.code} is {lot.state.value}")
    if lot.state is LotState.HELD:
        raise PolicyError(f"lot {lot.code} is held: {lot.note}", rule="movement.held")


def move_container(
    lot: RearingLot,
    destination: Container,
    day: object,
    moved_by: str,
) -> Transfer:
    """Move a whole lot into another unit.

    No ledger entry, because no fish left or joined the lot. The unit it is
    sitting in is a property of the lot, and the ledger accounts for fish.
    """

    _check_movable(lot)
    destination.check_available()
    if destination.code == lot.container:
        raise ValidationError("that lot is already in that unit", field="destination")
    origin = lot.container
    when = parse_date(day)
    if not moved_by.strip():
        raise ValidationError("a movement needs whoever made it", field="moved_by")
    lot.move_to(destination.code)
    return Transfer(
        day=when,
        lot=str(lot.code),
        fish=lot.population,
        origin=origin,
        destination=destination.code,
        moved_by=moved_by.strip(),
    )


def split_lot(
    lot: RearingLot,
    destination: Container,
    ledger: Ledger,
    day: object,
    fish: Number,
    suffix: str,
    moved_by: str,
) -> tuple[RearingLot, Transfer]:
    """Take part of a lot into a unit of its own, writing both sides."""

    _check_movable(lot)
    destination.check_available()
    count = require_positive(fish, field="fish")
    if count >= lot.population:
        raise ValidationError(
            f"a split of {count} leaves nothing of the {lot.population} standing", field="fish"
        )
    when = parse_date(day)
    if not moved_by.strip():
        raise ValidationError("a split needs whoever made it", field="moved_by")
    child_text = split_suffix(str(lot.code), suffix)
    child_code = LotCode(lot.code.year, lot.code.species, lot.code.sequence)
    child = RearingLot(
        code=child_code,
        container=destination.code,
        ponded_on=lot.ponded_on,
        population=count,
        mean_weight=lot.mean_weight,
        origin_egg_lot=lot.origin_egg_lot,
    )
    lot.remove(count)
    ledger.record(
        LedgerEntry(
            day=when,
            lot=str(lot.code),
            kind=EntryKind.TRANSFER_OUT,
            count=count,
            entered_by=moved_by,
            counterparty=destination.code,
        )
    )
    ledger.record(
        LedgerEntry(
            day=when,
            lot=child_text,
            kind=EntryKind.TRANSFER_IN,
            count=count,
            entered_by=moved_by,
            counterparty=lot.container,
        )
    )
    return child, Transfer(
        day=when,
        lot=child_text,
        fish=count,
        origin=lot.container,
        destination=destination.code,
        moved_by=moved_by.strip(),
    )


def merge_lots(
    keep: RearingLot,
    absorb: RearingLot,
    ledger: Ledger,
    day: object,
    moved_by: str,
) -> Transfer:
    """Put one lot into another, keeping the larger lot's identity."""

    _check_movable(keep)
    _check_movable(absorb)
    if keep.code == absorb.code:
        raise ValidationError("a lot cannot be merged into itself", field="absorb")
    if keep.code.species != absorb.code.species:
        raise PolicyError(
            f"{keep.code} and {absorb.code} are different species", rule="movement.species"
        )
    if absorb.population > keep.population:
        raise ValidationError("merge into the larger lot, not out of it", field="keep")
    when = parse_date(day)
    moving = absorb.population
    origin = absorb.container
    keep.add(moving, absorb.mean_weight)
    absorb.remove(moving, reason=f"merged into {keep.code}")
    ledger.record(
        LedgerEntry(
            day=when,
            lot=str(absorb.code),
            kind=EntryKind.TRANSFER_OUT,
            count=moving,
            entered_by=moved_by,
            counterparty=keep.container,
        )
    )
    ledger.record(
        LedgerEntry(
            day=when,
            lot=str(keep.code),
            kind=EntryKind.TRANSFER_IN,
            count=moving,
            entered_by=moved_by,
            counterparty=origin,
        )
    )
    return Transfer(
        day=when,
        lot=str(keep.code),
        fish=moving,
        origin=origin,
        destination=keep.container,
        moved_by=moved_by.strip(),
    )


def blended_weight(first: RearingLot, second: RearingLot) -> Quantity:
    """What the mean weight would be if two lots were put together."""

    total = (
        first.population * first.mean_weight.to("g").amount
        + second.population * second.mean_weight.to("g").amount
    )
    population = first.population + second.population
    if population == 0:
        raise ValidationError("two empty lots have no mean weight", field="population")
    return Quantity(total / population, "g")


def evens_out(first: RearingLot, second: RearingLot) -> Decimal:
    """How far apart two lots are in mean weight, as a share of the larger.

    Merging lots that are too far apart in size is how a station gets a raceway
    where the big fish eat the feed and the small ones stay small.
    """

    left = first.mean_weight.to("g").amount
    right = second.mean_weight.to("g").amount
    biggest = max(left, right)
    if biggest == 0:
        raise ValidationError("neither lot has a weight", field="mean_weight")
    return abs(left - right) / biggest
