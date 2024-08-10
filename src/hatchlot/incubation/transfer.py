"""Moving eggs, splitting a lot, and ponding what comes out of it.

Three movements happen in an incubation room and they are not the same. A
transfer moves eggs between vessels and changes nothing about the lot. A split
takes part of a lot and makes a new lot out of it, which is what happens when
half a take goes to another station. Ponding ends the lot: the fish come out of
the vessel and become a rearing lot somewhere else.

All three go through the tender check, because the whole point of that rule is
that it applies to everybody including the person in a hurry.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from enum import Enum

from ..calendar import parse_date
from ..errors import StateError, ValidationError
from ..identifiers import LotCode, normalise_code, split_suffix
from ..numeric import Number, require_non_negative, require_positive
from ..species import Species
from .development import check_handling
from .eggslot import EggLot, EggStage, LossCause
from .vessel import VesselRegister


class MovementKind(Enum):
    """What kind of movement was made."""

    TRANSFER = "transfer"
    SPLIT = "split"
    POND = "pond"
    SHIP = "ship"


@dataclass(frozen=True, slots=True)
class Movement:
    """One movement, written down the way an inventory can replay it."""

    day: date
    kind: MovementKind
    lot: str
    eggs: Decimal
    origin: str
    destination: str
    moved_by: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "day", parse_date(self.day))
        object.__setattr__(self, "lot", normalise_code(self.lot, field="lot"))
        object.__setattr__(self, "eggs", require_positive(self.eggs, field="eggs"))
        if not self.moved_by.strip():
            raise ValidationError("a movement needs whoever made it", field="moved_by")
        object.__setattr__(self, "moved_by", self.moved_by.strip())


def transfer(
    room: VesselRegister,
    lot: EggLot,
    day: object,
    eggs: Number,
    origin: str,
    destination: str,
    moved_by: str,
    species: Species,
    units_accumulated: Number,
    *,
    eggs_per_litre: Number | None = None,
) -> Movement:
    """Move part of a lot from one vessel to another."""

    check_handling(units_accumulated, species)
    if lot.stage.is_closed:
        raise StateError(f"lot {lot.code} is {lot.stage.value} and does not move")
    amount = require_positive(eggs, field="eggs")
    source = room.get(origin)
    target = room.get(destination)
    if source.code == target.code:
        raise ValidationError("a transfer needs two different vessels", field="destination")
    source.unload(str(lot.code), amount)
    target.load(str(lot.code), amount, eggs_per_litre)
    return Movement(
        day=parse_date(day),
        kind=MovementKind.TRANSFER,
        lot=str(lot.code),
        eggs=amount,
        origin=source.code,
        destination=target.code,
        moved_by=moved_by,
    )


def split(
    lot: EggLot,
    day: object,
    eggs: Number,
    suffix: str,
    moved_by: str,
    species: Species,
    units_accumulated: Number,
) -> tuple[EggLot, Movement]:
    """Take part of a lot out into a lot of its own.

    The parent keeps its history, and the child starts from the eggs it was
    given rather than inheriting a green count it never had. That is deliberate:
    a split lot's survival is only honest against what it actually received.
    """

    check_handling(units_accumulated, species)
    if lot.stage.is_closed:
        raise StateError(f"lot {lot.code} is {lot.stage.value} and cannot be split")
    amount = require_positive(eggs, field="eggs")
    if amount >= lot.count:
        raise ValidationError(
            f"a split of {amount} leaves nothing of the {lot.count} standing", field="eggs"
        )
    when = parse_date(day)
    lot.record_loss(when, amount, LossCause.HANDLING)
    child_code = split_suffix(str(lot.code), suffix)
    parts = child_code.split("-")
    child = EggLot(
        code=LotCode(parts[0], parts[1], parts[2][: -len(suffix)] or parts[2]),
        take=lot.take,
        species=lot.species,
        spawned_on=lot.spawned_on,
        green_count=amount,
        stage=lot.stage,
        unit=lot.unit,
    )
    movement = Movement(
        day=when,
        kind=MovementKind.SPLIT,
        lot=str(lot.code),
        eggs=amount,
        origin=lot.unit or "-",
        destination=child_code,
        moved_by=moved_by,
    )
    return child, movement


def pond(
    room: VesselRegister,
    lot: EggLot,
    day: object,
    destination: str,
    moved_by: str,
    species: Species,
    units_accumulated: Number,
) -> Movement:
    """Take a lot out of incubation and hand it to a rearing unit."""

    check_handling(units_accumulated, species)
    if lot.stage is not EggStage.HATCHED:
        raise StateError(f"lot {lot.code} is {lot.stage.value} and is not ready to pond")
    taken = require_non_negative(units_accumulated, field="units_accumulated")
    if taken < species.swim_up_units:
        raise ValidationError(
            f"lot {lot.code} is at {taken} units and swims up at {species.swim_up_units}",
            field="units_accumulated",
        )
    standing = lot.count
    for vessel in room.holding(str(lot.code)):
        vessel.unload(str(lot.code))
    lot.advance(EggStage.PONDED)
    lot.unit = normalise_code(destination, field="destination")
    return Movement(
        day=parse_date(day),
        kind=MovementKind.POND,
        lot=str(lot.code),
        eggs=standing,
        origin="incubation",
        destination=lot.unit,
        moved_by=moved_by,
    )


def movement_total(movements: list[Movement], kind: MovementKind) -> Decimal:
    return sum((move.eggs for move in movements if move.kind is kind), Decimal(0))
