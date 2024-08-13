"""Making the lot records and the trays agree.

Two counts exist for every lot and they are written by different people. The lot
carries a number that started at the take and has had losses taken off it. The
vessels carry whatever somebody put in them. They drift apart, and the drift is
always found in January when a truck is already booked.

This is the reconciliation, and it reports three separate problems rather than
one number: lots nobody can find, eggs in a tray belonging to no lot, and counts
that disagree by more than the station tolerates.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from ..errors import ValidationError
from ..numeric import Number, percent_difference, require_non_negative
from .eggslot import EggLot
from .vessel import VesselRegister


@dataclass(frozen=True, slots=True)
class Discrepancy:
    """One lot whose two counts do not agree."""

    lot: str
    on_record: Decimal
    in_vessels: Decimal

    @property
    def difference(self) -> Decimal:
        return self.in_vessels - self.on_record

    @property
    def percent(self) -> Decimal:
        if self.on_record == 0:
            return Decimal(100) if self.in_vessels != 0 else Decimal(0)
        return percent_difference(self.in_vessels, self.on_record)

    @property
    def direction(self) -> str:
        return "over" if self.difference > 0 else "short"


@dataclass(frozen=True, slots=True)
class Reconciliation:
    """The whole room, checked."""

    checked: int
    discrepancies: tuple[Discrepancy, ...]
    missing_from_vessels: tuple[str, ...]
    unknown_in_vessels: tuple[str, ...]
    tolerance: Decimal

    @property
    def is_clean(self) -> bool:
        return not (self.discrepancies or self.missing_from_vessels or self.unknown_in_vessels)

    @property
    def worst(self) -> Discrepancy | None:
        if not self.discrepancies:
            return None
        return max(self.discrepancies, key=lambda entry: abs(entry.percent))

    def line(self) -> str:
        return (
            f"{self.checked} lots checked, {len(self.discrepancies)} disagree, "
            f"{len(self.missing_from_vessels)} not in a vessel, "
            f"{len(self.unknown_in_vessels)} unknown in the room"
        )


def reconcile_room(
    lots: list[EggLot], room: VesselRegister, *, tolerance_percent: Number = 1
) -> Reconciliation:
    """Check every lot against what the trays say, inside a tolerance."""

    tolerance = require_non_negative(tolerance_percent, field="tolerance_percent")
    known = {str(lot.code): lot for lot in lots}
    if len(known) != len(lots):
        raise ValidationError("the same lot appears twice", field="lots")
    discrepancies: list[Discrepancy] = []
    missing: list[str] = []
    for code, lot in sorted(known.items()):
        if lot.stage.is_closed:
            continue
        in_vessels = room.eggs_of(code)
        if in_vessels == 0:
            missing.append(code)
            continue
        entry = Discrepancy(lot=code, on_record=lot.count, in_vessels=in_vessels)
        if abs(entry.percent) > tolerance:
            discrepancies.append(entry)
    in_room: set[str] = set()
    for vessel in room.all():
        in_room.update(vessel.contents)
    unknown = sorted(code for code in in_room if code not in known)
    return Reconciliation(
        checked=len([lot for lot in lots if not lot.stage.is_closed]),
        discrepancies=tuple(discrepancies),
        missing_from_vessels=tuple(missing),
        unknown_in_vessels=tuple(unknown),
        tolerance=tolerance,
    )


def room_total(room: VesselRegister) -> Decimal:
    """Every egg the trays say the room is holding."""

    return sum((vessel.loaded for vessel in room.all()), Decimal(0))


def record_total(lots: list[EggLot]) -> Decimal:
    """Every egg the lot records say the room is holding."""

    return sum((lot.count for lot in lots if not lot.stage.is_closed), Decimal(0))


def occupancy(room: VesselRegister, eggs_per_litre: Number | None = None) -> Decimal:
    """How full the room is, across everything in it."""

    capacity = Decimal(0)
    for vessel in room.all():
        try:
            capacity += vessel.capacity(eggs_per_litre)
        except ValidationError:
            continue
    if capacity == 0:
        raise ValidationError("the room has no capacity to be a share of", field="room")
    return room_total(room) / capacity
