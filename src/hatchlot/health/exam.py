"""Health examinations, and turning a page of observations into a number.

A fish health inspection is a person looking at thirty fish and writing down what
they see: gill condition, parasites, lesions, fin damage. Every one of those is
scored on a small scale, and the useful output is not any single score but the
prevalence across the sample and the severity where it was found.

Those two are separate on purpose. Half the fish carrying a light gill score is a
water quality problem. Two fish with a severe one is a different conversation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from enum import Enum

from ..calendar import parse_date
from ..errors import ValidationError
from ..identifiers import normalise_code
from ..numeric import Number, require_positive, safe_divide, to_decimal


class Finding(Enum):
    """What an inspector looks for, in the categories the report uses."""

    GILL = "gill"
    PARASITE = "parasite"
    LESION = "lesion"
    FIN = "fin"
    EYE = "eye"
    BEHAVIOUR = "behaviour"

    @property
    def is_external(self) -> bool:
        return self is not Finding.BEHAVIOUR


class Severity(Enum):
    """How bad it was, on the scale the inspection sheet uses."""

    NONE = 0
    SLIGHT = 1
    MODERATE = 2
    SEVERE = 3

    @property
    def is_present(self) -> bool:
        return self is not Severity.NONE

    @classmethod
    def from_score(cls, score: Number) -> Severity:
        value = to_decimal(score, field="score")
        if value != value.to_integral_value() or not 0 <= value <= 3:
            raise ValidationError(f"{score!r} is not a severity score", field="score")
        return cls(int(value))


@dataclass(frozen=True, slots=True)
class Observation:
    """One fish, one finding, one score."""

    fish: int
    finding: Finding
    severity: Severity

    def __post_init__(self) -> None:
        if self.fish < 1:
            raise ValidationError("fish are numbered from one", field="fish")
        if not isinstance(self.finding, Finding):
            raise ValidationError(f"{self.finding!r} is not a finding", field="finding")
        if not isinstance(self.severity, Severity):
            raise ValidationError(f"{self.severity!r} is not a severity", field="severity")


@dataclass
class Examination:
    """One inspection of one lot."""

    code: str
    lot: str
    day: date
    fish_examined: int
    inspector: str
    observations: list[Observation] = field(default_factory=list)
    note: str = ""

    def __post_init__(self) -> None:
        self.code = normalise_code(self.code, field="examination")
        self.lot = normalise_code(self.lot, field="lot")
        self.day = parse_date(self.day)
        if self.fish_examined < 1:
            raise ValidationError("an examination looks at fish", field="fish_examined")
        if not self.inspector.strip():
            raise ValidationError("an examination needs an inspector", field="inspector")
        self.inspector = self.inspector.strip()

    def record(self, observation: Observation) -> Observation:
        """File an observation, refusing a fish outside the sample."""

        if observation.fish > self.fish_examined:
            raise ValidationError(
                f"fish {observation.fish} is outside a sample of {self.fish_examined}",
                field="fish",
            )
        for existing in self.observations:
            if existing.fish == observation.fish and existing.finding is observation.finding:
                raise ValidationError(
                    f"fish {observation.fish} already has a {observation.finding.value} score",
                    field="finding",
                )
        self.observations.append(observation)
        return observation

    def score(self, fish: int, finding: Finding, severity: Number) -> Observation:
        return self.record(
            Observation(fish=fish, finding=finding, severity=Severity.from_score(severity))
        )

    def for_finding(self, finding: Finding) -> tuple[Observation, ...]:
        return tuple(entry for entry in self.observations if entry.finding is finding)

    def prevalence(self, finding: Finding) -> Decimal:
        """The share of the sample carrying a finding at all."""

        affected = len([entry for entry in self.for_finding(finding) if entry.severity.is_present])
        return safe_divide(affected, self.fish_examined, field="fish_examined")

    def mean_severity(self, finding: Finding) -> Decimal:
        """The mean score across the fish that had it, not across the sample."""

        present = [entry for entry in self.for_finding(finding) if entry.severity.is_present]
        if not present:
            return Decimal(0)
        total = sum((Decimal(entry.severity.value) for entry in present), Decimal(0))
        return total / Decimal(len(present))

    def worst(self, finding: Finding) -> Severity:
        scores = [entry.severity for entry in self.for_finding(finding)]
        return max(scores, key=lambda severity: severity.value) if scores else Severity.NONE

    def findings_present(self) -> tuple[Finding, ...]:
        return tuple(finding for finding in Finding if self.prevalence(finding) > 0)

    def is_clean(self) -> bool:
        return not self.findings_present()


def is_sample_adequate(exam: Examination, population: Number, *, minimum: int = 30) -> bool:
    """Whether the sample was big enough to say anything about the lot."""

    held = require_positive(population, field="population")
    if exam.fish_examined >= held:
        return True
    return exam.fish_examined >= minimum


def worst_of(exams: list[Examination], finding: Finding) -> Examination | None:
    """The examination with the highest prevalence of a finding."""

    if not exams:
        return None
    return max(exams, key=lambda exam: exam.prevalence(finding))
