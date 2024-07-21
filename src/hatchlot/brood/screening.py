"""Pathogen screening on the females, and what it does to their eggs.

Every female spawned is sampled, and the eggs sit held until the results come
back. Two things then decide what happens, and they are not the same thing: how
bad the worst individual result is, and how much of the take is affected. A
single high female in a big take is a segregation problem. Half the take reading
moderate is a destruction problem even though no single fish is as bad.

That interaction is the whole module. Everything else is bookkeeping.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum

from ..errors import DuplicateError, ValidationError
from ..identifiers import normalise_code
from ..numeric import Number, require_non_negative, require_range


class Pathogen(Enum):
    """The organisms a coldwater station screens for."""

    IHNV = "ihnv"
    IPNV = "ipnv"
    BKD = "bkd"
    FURUNCULOSIS = "furunculosis"
    WHIRLING = "whirling"

    @property
    def is_vertically_transmitted(self) -> bool:
        """Whether the pathogen can ride inside the egg, which changes everything."""

        return self in {Pathogen.IHNV, Pathogen.IPNV, Pathogen.BKD}


class AssayLevel(Enum):
    """An ELISA read, banded the way a fish health lab reports it."""

    PENDING = "pending"
    NEGATIVE = "negative"
    LOW = "low"
    MODERATE = "moderate"
    HIGH = "high"

    @property
    def rank(self) -> int:
        return {"pending": -1, "negative": 0, "low": 1, "moderate": 2, "high": 3}[self.value]

    @property
    def is_positive(self) -> bool:
        return self.rank >= 1


class Disposition(Enum):
    """What the eggs of a screened take may do."""

    RELEASE = "release"
    SEGREGATE = "segregate"
    DESTROY = "destroy"
    WAIT = "wait"


# Optical density thresholds for the banding above. A lab reports the number;
# the band is the station's reading of it, so the cuts live here and not there.
LOW_CUT = Decimal("0.10")
MODERATE_CUT = Decimal("0.20")
HIGH_CUT = Decimal("0.50")


def band(optical_density: Number) -> AssayLevel:
    """Band an optical density into the level a report carries."""

    value = require_non_negative(optical_density, field="optical_density")
    if value >= HIGH_CUT:
        return AssayLevel.HIGH
    if value >= MODERATE_CUT:
        return AssayLevel.MODERATE
    if value >= LOW_CUT:
        return AssayLevel.LOW
    return AssayLevel.NEGATIVE


@dataclass(frozen=True, slots=True)
class Assay:
    """One female's result for one pathogen."""

    tag: str
    pathogen: Pathogen
    level: AssayLevel

    def __post_init__(self) -> None:
        object.__setattr__(self, "tag", normalise_code(self.tag, field="tag"))
        if not isinstance(self.pathogen, Pathogen):
            raise ValidationError(f"{self.pathogen!r} is not a pathogen", field="pathogen")
        if not isinstance(self.level, AssayLevel):
            raise ValidationError(f"{self.level!r} is not an assay level", field="level")

    @classmethod
    def from_density(cls, tag: str, pathogen: Pathogen, optical_density: Number) -> Assay:
        return cls(tag=tag, pathogen=pathogen, level=band(optical_density))


@dataclass
class Screen:
    """The screening of one take: every female, every pathogen looked for."""

    take: str
    pathogens: tuple[Pathogen, ...]
    assays: list[Assay] = field(default_factory=list)
    females_spawned: int = 0

    def __post_init__(self) -> None:
        self.take = normalise_code(self.take, field="take")
        if not self.pathogens:
            raise ValidationError("a screen looks for something", field="pathogens")
        if self.females_spawned < 0:
            raise ValidationError("a take cannot spawn a negative number", field="females")

    def record(self, assay: Assay) -> Assay:
        """File a result, refusing a second result for the same fish and pathogen."""

        if assay.pathogen not in self.pathogens:
            raise ValidationError(f"{assay.pathogen.value} is not on this screen", field="pathogen")
        for existing in self.assays:
            if existing.tag == assay.tag and existing.pathogen is assay.pathogen:
                raise DuplicateError("assay", f"{assay.tag}/{assay.pathogen.value}")
        self.assays.append(assay)
        return assay

    def for_pathogen(self, pathogen: Pathogen) -> tuple[Assay, ...]:
        return tuple(assay for assay in self.assays if assay.pathogen is pathogen)

    def females_tested(self) -> int:
        return len({assay.tag for assay in self.assays})

    def is_complete(self) -> bool:
        """Whether every spawned female has a result for every pathogen."""

        if self.females_spawned == 0:
            return False
        expected = self.females_spawned * len(self.pathogens)
        settled = [assay for assay in self.assays if assay.level is not AssayLevel.PENDING]
        return len(settled) >= expected

    def worst(self, pathogen: Pathogen) -> AssayLevel:
        results = self.for_pathogen(pathogen)
        if not results:
            return AssayLevel.PENDING
        return max((assay.level for assay in results), key=lambda level: level.rank)

    def prevalence(self, pathogen: Pathogen) -> Decimal:
        """The share of tested females positive for a pathogen."""

        results = self.for_pathogen(pathogen)
        if not results:
            return Decimal(0)
        positive = sum(1 for assay in results if assay.level.is_positive)
        return require_range(Decimal(positive) / Decimal(len(results)), 0, 1, field="prevalence")


def disposition(
    screen: Screen,
    *,
    segregate_at: AssayLevel = AssayLevel.MODERATE,
    destroy_prevalence: Number = "0.5",
) -> Disposition:
    """Decide what the eggs may do, on the worst result and the prevalence together.

    The order matters. An incomplete screen waits whatever the partial results
    say, because releasing on a partial screen is the failure this whole module
    exists to prevent.
    """

    if not screen.is_complete():
        return Disposition.WAIT
    ceiling = require_range(destroy_prevalence, 0, 1, field="destroy_prevalence")
    verdict = Disposition.RELEASE
    for pathogen in screen.pathogens:
        worst = screen.worst(pathogen)
        prevalence = screen.prevalence(pathogen)
        if not pathogen.is_vertically_transmitted:
            continue
        if worst is AssayLevel.HIGH and prevalence >= ceiling:
            return Disposition.DESTROY
        if prevalence >= ceiling and worst.rank >= segregate_at.rank:
            return Disposition.DESTROY
        if worst.rank >= segregate_at.rank:
            verdict = Disposition.SEGREGATE
    return verdict
