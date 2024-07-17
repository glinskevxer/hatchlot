"""The spawn take: one day's work at the spawning shed.

A take is the join between the females that were spawned, the males that
fertilised them, and the eggs that came out. It is also where the first hold
goes on: eggs from a take whose females have not cleared their pathogen screen
cannot go into a shared incubation water, so a take stays held until somebody
with a name on it releases it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from enum import Enum

from ..calendar import DateRange, parse_date
from ..errors import DuplicateError, NotFoundError, StateError, ValidationError
from ..identifiers import normalise_code, normalise_species
from ..numeric import safe_divide
from ..quantities.temperature import Temperature
from ..species import resolve_species
from .eggcount import CountMethod, EggEstimate


class TakeState(Enum):
    """Where a take is in its own paperwork."""

    OPEN = "open"
    CLOSED = "closed"
    HELD = "held"
    RELEASED = "released"
    DESTROYED = "destroyed"

    @property
    def accepts_eggs(self) -> bool:
        return self is TakeState.OPEN


@dataclass
class SpawnTake:
    """One day of spawning, from the first female to the released egg lot."""

    code: str
    day: date
    species: str
    water: Temperature
    spawned_by: str
    females: list[str] = field(default_factory=list)
    males: list[str] = field(default_factory=list)
    estimate: EggEstimate | None = None
    state: TakeState = TakeState.OPEN
    released_by: str = ""
    note: str = ""

    def __post_init__(self) -> None:
        self.code = normalise_code(self.code, field="take")
        self.day = parse_date(self.day)
        self.species = normalise_species(self.species)
        if not self.spawned_by.strip():
            raise ValidationError("a take needs whoever ran it", field="spawned_by")
        self.spawned_by = self.spawned_by.strip()

    def add_female(self, tag: str) -> str:
        """Put a spawned female on the take."""

        if not self.state.accepts_eggs:
            raise StateError(f"take {self.code} is {self.state.value} and takes no more females")
        code = normalise_code(tag, field="tag")
        if code in self.females:
            raise DuplicateError("female on take", code)
        self.females.append(code)
        return code

    def add_male(self, tag: str) -> str:
        if not self.state.accepts_eggs:
            raise StateError(f"take {self.code} is {self.state.value} and takes no more males")
        code = normalise_code(tag, field="tag")
        if code in self.males:
            raise DuplicateError("male on take", code)
        self.males.append(code)
        return code

    def close(self, estimate: EggEstimate) -> None:
        """Shut the take with a count on it."""

        if self.state is not TakeState.OPEN:
            raise StateError(f"take {self.code} is already {self.state.value}")
        if not self.females:
            raise StateError(f"take {self.code} has no females on it")
        if not self.males:
            raise StateError(f"take {self.code} has no males on it")
        if not isinstance(estimate, EggEstimate):
            raise ValidationError("a take closes on an egg estimate", field="estimate")
        self.estimate = estimate
        self.state = TakeState.HELD

    def release(self, released_by: str) -> None:
        """Let the eggs go to incubation, with a name against the decision."""

        if self.state is not TakeState.HELD:
            raise StateError(f"take {self.code} is {self.state.value} and cannot be released")
        if not released_by.strip():
            raise ValidationError("a release needs a name", field="released_by")
        self.released_by = released_by.strip()
        self.state = TakeState.RELEASED

    def destroy(self, reason: str) -> None:
        """Write the take off, which a failed screen forces."""

        if self.state is TakeState.RELEASED:
            raise StateError(f"take {self.code} has already gone to incubation")
        if not reason.strip():
            raise ValidationError("writing off a take needs a reason", field="reason")
        self.note = reason.strip()
        self.state = TakeState.DESTROYED

    @property
    def green_eggs(self) -> Decimal:
        return self.estimate.eggs if self.estimate is not None else Decimal(0)

    @property
    def eggs_per_female(self) -> Decimal:
        if not self.females:
            raise ValidationError("no females on the take", field="females")
        return safe_divide(self.green_eggs, len(self.females), field="females")

    @property
    def is_finished(self) -> bool:
        return self.state in {TakeState.RELEASED, TakeState.DESTROYED}


class TakeRegister:
    """Every take of a season, keyed by code."""

    def __init__(self) -> None:
        self._takes: dict[str, SpawnTake] = {}

    def add(self, take: SpawnTake) -> SpawnTake:
        if take.code in self._takes:
            raise DuplicateError("take", take.code)
        self._takes[take.code] = take
        return take

    def get(self, code: str) -> SpawnTake:
        key = normalise_code(code, field="take")
        try:
            return self._takes[key]
        except KeyError:
            raise NotFoundError("take", key) from None

    def __len__(self) -> int:
        return len(self._takes)

    def all(self) -> tuple[SpawnTake, ...]:
        return tuple(sorted(self._takes.values(), key=lambda take: (take.day, take.code)))

    def within(self, window: DateRange) -> tuple[SpawnTake, ...]:
        return tuple(take for take in self.all() if take.day in window)

    def in_state(self, state: TakeState) -> tuple[SpawnTake, ...]:
        return tuple(take for take in self.all() if take.state is state)

    def for_species(self, species: str) -> tuple[SpawnTake, ...]:
        code = resolve_species(species).code
        return tuple(take for take in self.all() if take.species == code)

    def green_eggs(self, species: str | None = None) -> Decimal:
        """Total eggs taken, optionally for one species, counting released takes only."""

        takes = self.for_species(species) if species else self.all()
        return sum(
            (take.green_eggs for take in takes if take.state is TakeState.RELEASED), Decimal(0)
        )

    def females_used(self) -> int:
        return sum(len(take.females) for take in self.all())

    def held(self) -> tuple[SpawnTake, ...]:
        """Everything waiting on somebody, which is the list that runs the shed."""

        return self.in_state(TakeState.HELD)


def enumerate_take(take: SpawnTake, eggs: int) -> EggEstimate:
    """Close a take on a hand count, which small takes really are."""

    estimate = EggEstimate(eggs, CountMethod.ENUMERATED)
    take.close(estimate)
    return estimate
