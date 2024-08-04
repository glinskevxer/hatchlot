"""The egg lot, which is the unit everything in the incubation room counts in.

An egg lot is created from a spawn take and dies when the fish are ponded. In
between it loses eggs to picking, to shocking and to whatever the water does,
and every one of those has to come off the count in the right order. The lot
keeps the running number and refuses to go negative, because an incubation room
that can go negative is an incubation room whose numbers nobody trusts.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from enum import Enum

from ..calendar import parse_date
from ..errors import StateError, ValidationError
from ..identifiers import LotCode, normalise_code, normalise_species
from ..numeric import Number, require_non_negative, require_positive, safe_divide


class EggStage(Enum):
    """Where a lot is in incubation, in the order it goes through them."""

    GREEN = "green"
    EYED = "eyed"
    HATCHED = "hatched"
    PONDED = "ponded"
    WRITTEN_OFF = "written_off"

    @property
    def order(self) -> int:
        return {"green": 0, "eyed": 1, "hatched": 2, "ponded": 3, "written_off": 4}[self.value]

    @property
    def is_closed(self) -> bool:
        return self in {EggStage.PONDED, EggStage.WRITTEN_OFF}


class LossCause(Enum):
    """Why eggs came off the count."""

    PICKED = "picked"
    SHOCK = "shock"
    UNFERTILISED = "unfertilised"
    FUNGUS = "fungus"
    HANDLING = "handling"
    ACCIDENT = "accident"


@dataclass(frozen=True, slots=True)
class LossEntry:
    """One deduction from the count, with the day and the reason on it."""

    day: date
    count: Decimal
    cause: LossCause
    stage: EggStage

    def __post_init__(self) -> None:
        object.__setattr__(self, "day", parse_date(self.day))
        object.__setattr__(self, "count", require_positive(self.count, field="count"))
        if not isinstance(self.cause, LossCause):
            raise ValidationError(f"{self.cause!r} is not a loss cause", field="cause")


@dataclass
class EggLot:
    """One lot of eggs, from the take that made it to the fish that leave it."""

    code: LotCode
    take: str
    species: str
    spawned_on: date
    green_count: Decimal
    stage: EggStage = EggStage.GREEN
    unit: str = ""
    losses: list[LossEntry] = field(default_factory=list)
    note: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.code, LotCode):
            raise ValidationError("an egg lot needs a lot code", field="code")
        self.take = normalise_code(self.take, field="take")
        self.species = normalise_species(self.species)
        self.spawned_on = parse_date(self.spawned_on)
        self.green_count = require_positive(self.green_count, field="green_count")
        if self.unit:
            self.unit = normalise_code(self.unit, field="unit")

    @property
    def lost(self) -> Decimal:
        return sum((entry.count for entry in self.losses), Decimal(0))

    @property
    def count(self) -> Decimal:
        """Eggs still on the lot."""

        return self.green_count - self.lost

    @property
    def survival(self) -> Decimal:
        """The share of the green count still alive."""

        return safe_divide(self.count, self.green_count, field="green_count")

    def lost_to(self, cause: LossCause) -> Decimal:
        return sum((entry.count for entry in self.losses if entry.cause is cause), Decimal(0))

    def lost_at(self, stage: EggStage) -> Decimal:
        return sum((entry.count for entry in self.losses if entry.stage is stage), Decimal(0))

    def record_loss(self, day: object, count: Number, cause: LossCause) -> LossEntry:
        """Take eggs off the count, refusing more than are there."""

        if self.stage.is_closed:
            raise StateError(f"lot {self.code} is {self.stage.value} and takes no more losses")
        amount = require_positive(count, field="count")
        if amount > self.count:
            raise ValidationError(
                f"cannot lose {amount} eggs from a lot holding {self.count}", field="count"
            )
        entry = LossEntry(day=parse_date(day), count=amount, cause=cause, stage=self.stage)
        if self.losses and entry.day < self.losses[-1].day:
            raise ValidationError("a loss cannot precede the one before it", field="day")
        self.losses.append(entry)
        return entry

    def advance(self, stage: EggStage) -> EggStage:
        """Move the lot on, forwards only."""

        if not isinstance(stage, EggStage):
            raise ValidationError(f"{stage!r} is not a stage", field="stage")
        if self.stage.is_closed:
            raise StateError(f"lot {self.code} is already {self.stage.value}")
        if stage is not EggStage.WRITTEN_OFF and stage.order <= self.stage.order:
            raise StateError(f"lot {self.code} cannot go back to {stage.value}")
        self.stage = stage
        return stage

    def write_off(self, reason: str) -> None:
        if not reason.strip():
            raise ValidationError("writing off a lot needs a reason", field="reason")
        self.advance(EggStage.WRITTEN_OFF)
        self.note = reason.strip()

    def move_to(self, unit: str) -> str:
        if self.stage.is_closed:
            raise StateError(f"lot {self.code} is {self.stage.value} and does not move")
        self.unit = normalise_code(unit, field="unit")
        return self.unit

    def loss_rate(self, cause: LossCause) -> Decimal:
        return safe_divide(self.lost_to(cause), self.green_count, field="green_count")

    def days_incubating(self, as_of: object) -> int:
        day = parse_date(as_of)
        if day < self.spawned_on:
            raise ValidationError("that is before the eggs were taken", field="as_of")
        return (day - self.spawned_on).days


def total_eggs(lots: list[EggLot]) -> Decimal:
    return sum((lot.count for lot in lots), Decimal(0))


def combined_survival(lots: list[EggLot]) -> Decimal:
    """Survival across a set of lots, weighted by their green counts."""

    if not lots:
        raise ValidationError("no lots to combine", field="lots")
    green = sum((lot.green_count for lot in lots), Decimal(0))
    return safe_divide(total_eggs(lots), require_non_negative(green, field="green"), field="green")
