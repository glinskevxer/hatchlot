"""The broodstock female, and the state she moves through in a spawning season.

A female is checked over and over through the run. Each check either finds her
still green, finds her ripe and takes her, or finds a reason to cull her. The
order those can happen in is the whole record, so it is a state machine rather
than a status column somebody overwrites.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from enum import Enum

from ..calendar import parse_date
from ..errors import StateError, ValidationError
from ..identifiers import normalise_code
from ..numeric import Number, require_positive, to_decimal
from ..quantities.base import Quantity


class Ripeness(Enum):
    """Where a female is in the run."""

    GREEN = "green"
    RIPE = "ripe"
    SPAWNED = "spawned"
    CULLED = "culled"
    MORTALITY = "mortality"

    @property
    def is_terminal(self) -> bool:
        return self in {Ripeness.SPAWNED, Ripeness.CULLED, Ripeness.MORTALITY}


_ALLOWED: dict[Ripeness, frozenset[Ripeness]] = {
    Ripeness.GREEN: frozenset({Ripeness.GREEN, Ripeness.RIPE, Ripeness.CULLED, Ripeness.MORTALITY}),
    Ripeness.RIPE: frozenset({Ripeness.SPAWNED, Ripeness.CULLED, Ripeness.MORTALITY}),
    Ripeness.SPAWNED: frozenset(),
    Ripeness.CULLED: frozenset(),
    Ripeness.MORTALITY: frozenset(),
}


class CullReason(Enum):
    """Why a female left the run without being spawned."""

    UNDERSIZE = "undersize"
    DISEASE = "disease"
    PRECOCIOUS = "precocious"
    SURPLUS = "surplus"
    OVERRIPE = "overripe"


@dataclass(frozen=True, slots=True)
class Check:
    """One handling: the day, what she was found to be, and who looked."""

    day: date
    ripeness: Ripeness
    checked_by: str
    note: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "day", parse_date(self.day))
        if not isinstance(self.ripeness, Ripeness):
            raise ValidationError(f"{self.ripeness!r} is not a ripeness", field="ripeness")
        if not self.checked_by.strip():
            raise ValidationError("a check needs whoever made it", field="checked_by")
        object.__setattr__(self, "checked_by", self.checked_by.strip())


@dataclass
class BroodFemale:
    """One female, her measurements, and every check made on her."""

    tag: str
    species: str
    length: Quantity
    weight: Quantity
    origin: str = "natural"
    checks: list[Check] = field(default_factory=list)
    cull_reason: CullReason | None = None

    def __post_init__(self) -> None:
        self.tag = normalise_code(self.tag, field="tag")
        self.species = normalise_code(self.species, field="species")
        require_positive(self.length.to("cm").amount, field="length")
        require_positive(self.weight.to("kg").amount, field="weight")
        if not self.origin.strip():
            raise ValidationError("a female needs an origin", field="origin")

    @property
    def ripeness(self) -> Ripeness:
        return self.checks[-1].ripeness if self.checks else Ripeness.GREEN

    @property
    def is_available(self) -> bool:
        return not self.ripeness.is_terminal

    @property
    def condition_factor(self) -> Decimal:
        """Fulton's K, on grams and centimetres, the way the form wants it."""

        grams = self.weight.to("g").amount
        centimetres = self.length.to("cm").amount
        return grams / (centimetres**3) * Decimal(100)

    def check(self, day: object, ripeness: Ripeness, checked_by: str, note: str = "") -> Check:
        """Record a handling, refusing a move the run does not allow."""

        if not isinstance(ripeness, Ripeness):
            raise ValidationError(f"{ripeness!r} is not a ripeness", field="ripeness")
        if ripeness not in _ALLOWED[self.ripeness]:
            raise StateError(
                f"{self.tag} is {self.ripeness.value} and cannot go to {ripeness.value}"
            )
        entry = Check(day=parse_date(day), ripeness=ripeness, checked_by=checked_by, note=note)
        if self.checks and entry.day < self.checks[-1].day:
            raise ValidationError("a check cannot precede the one before it", field="day")
        self.checks.append(entry)
        return entry

    def cull(self, day: object, reason: CullReason, checked_by: str) -> Check:
        """Take her out of the run, with the reason on the record."""

        if not isinstance(reason, CullReason):
            raise ValidationError(f"{reason!r} is not a cull reason", field="reason")
        entry = self.check(day, Ripeness.CULLED, checked_by, note=reason.value)
        self.cull_reason = reason
        return entry

    def spawned_on(self) -> date | None:
        for entry in self.checks:
            if entry.ripeness is Ripeness.SPAWNED:
                return entry.day
        return None

    def handling_count(self) -> int:
        """How many times she has been netted, which is a welfare number."""

        return len(self.checks)

    def days_held(self) -> int:
        """From the first check to the last, or zero if she has never been handled."""

        if len(self.checks) < 2:
            return 0
        return (self.checks[-1].day - self.checks[0].day).days


def mean_condition(females: list[BroodFemale]) -> Decimal:
    """Mean condition factor across a group, refusing an empty group."""

    if not females:
        raise ValidationError("no females to average", field="females")
    total = sum((female.condition_factor for female in females), Decimal(0))
    return total / Decimal(len(females))


def sort_by_size(females: list[BroodFemale], *, largest_first: bool = True) -> list[BroodFemale]:
    """Order a group by weight, which is how a spawning crew works a pen."""

    return sorted(females, key=lambda female: female.weight.to("kg").amount, reverse=largest_first)


def total_weight(females: list[BroodFemale], symbol: str = "kg") -> Quantity:
    total = Quantity(0, symbol)
    for female in females:
        total = total + female.weight
    return total


def parse_length(value: Number, symbol: str = "cm") -> Quantity:
    """Read a length off a measuring board, refusing a fish of no length."""

    return Quantity(require_positive(to_decimal(value, field="length"), field="length"), symbol)
