"""The broodstock register, and what a season adds up to.

The pieces of a spawning season live in their own modules and none of them can
answer the question the manager actually asks, which is whether the run is going
to make its egg target and what it is costing in fish. That join is here.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from ..calendar import DateRange
from ..errors import PolicyError, ValidationError
from ..numeric import Number, require_positive, safe_divide
from ..quantities.base import Quantity
from ..registry import CodeRegistry
from .fecundity import DEFAULT_MODEL, FecundityModel
from .female import BroodFemale, CullReason, Ripeness
from .take import SpawnTake, TakeRegister, TakeState


class BroodRegister(CodeRegistry[BroodFemale]):
    """Every female held this season, keyed by tag."""

    def __init__(self) -> None:
        super().__init__("female", lambda female: female.tag)

    def available(self) -> tuple[BroodFemale, ...]:
        return self.where(lambda female: female.is_available)

    def in_state(self, ripeness: Ripeness) -> tuple[BroodFemale, ...]:
        return self.where(lambda female: female.ripeness is ripeness)

    def culled_for(self, reason: CullReason) -> tuple[BroodFemale, ...]:
        return self.where(lambda female: female.cull_reason is reason)

    def biomass(self, symbol: str = "kg") -> Quantity:
        total = Quantity(0, symbol)
        for female in self.all():
            total = total + female.weight
        return total

    def expected_eggs(self, model: FecundityModel | None = None) -> Decimal:
        """What the females still in the run are expected to give."""

        curve = model or DEFAULT_MODEL
        return curve.expected_total([female.length for female in self.available()])

    def handling_load(self) -> Decimal:
        """Mean number of times a female has been netted, a welfare number."""

        females = self.all()
        if not females:
            raise ValidationError("no females on the register", field="females")
        total = Decimal(sum(female.handling_count() for female in females))
        return total / Decimal(len(females))


@dataclass(frozen=True, slots=True)
class SeasonSummary:
    """One season of spawning, from the register and the takes together."""

    window: DateRange
    females_held: int
    females_spawned: int
    females_culled: int
    takes_released: int
    takes_held: int
    green_eggs: Decimal
    target_eggs: Decimal

    @property
    def eggs_per_female(self) -> Decimal:
        if self.females_spawned == 0:
            return Decimal(0)
        return safe_divide(self.green_eggs, self.females_spawned, field="females_spawned")

    @property
    def target_share(self) -> Decimal:
        return safe_divide(self.green_eggs, self.target_eggs, field="target_eggs")

    @property
    def is_target_met(self) -> bool:
        return self.green_eggs >= self.target_eggs

    @property
    def cull_rate(self) -> Decimal:
        if self.females_held == 0:
            return Decimal(0)
        return Decimal(self.females_culled) / Decimal(self.females_held)

    def line(self) -> str:
        return (
            f"{self.window}: {self.females_spawned} spawned, "
            f"{self.green_eggs:.0f} eggs, {self.target_share:.0%} of target, "
            f"{self.takes_held} takes held"
        )


def summarise_season(
    females: BroodRegister,
    takes: TakeRegister,
    window: DateRange,
    target_eggs: Number,
) -> SeasonSummary:
    """Pull a season together, counting only the takes inside the window."""

    target = require_positive(target_eggs, field="target_eggs")
    inside = takes.within(window)
    released = [take for take in inside if take.state is TakeState.RELEASED]
    return SeasonSummary(
        window=window,
        females_held=len(females),
        females_spawned=sum(len(take.females) for take in released),
        females_culled=len(females.in_state(Ripeness.CULLED)),
        takes_released=len(released),
        takes_held=len([take for take in inside if take.state is TakeState.HELD]),
        green_eggs=sum((take.green_eggs for take in released), Decimal(0)),
        target_eggs=target,
    )


def check_take_against_register(take: SpawnTake, females: BroodRegister) -> None:
    """Refuse a take that names a female the register does not have in the run.

    The two records are written by different people at different times, and the
    place they disagree is always a fish that was culled on Tuesday and spawned
    on Wednesday.
    """

    for tag in take.females:
        female = females.find(tag)
        if female is None:
            raise PolicyError(f"{tag} is not on the register", rule="take.unknown_female")
        if female.ripeness is Ripeness.CULLED:
            raise PolicyError(f"{tag} was culled and cannot be spawned", rule="take.culled_female")
