"""Marking runs, and the quality check that has to follow one.

A trailer comes to the station, the fish go through it, and a number of them come
out the other side marked. That number is never the number that went in. Tags
fail to fire, fish go through twice, and the clip machine misses. So a run is not
finished when the fish are back in the raceway; it is finished when a sample has
been checked and the rate is known.

A run whose check comes back under the plan is not a failure to be noted. It is a
run that has to be done again on the fish that were missed, which is why the
shortfall is a number this module works out rather than a flag it sets.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal
from enum import Enum

from ..calendar import parse_date
from ..errors import PolicyError, StateError, ValidationError
from ..identifiers import normalise_code
from ..numeric import Number, require_positive, safe_divide, to_decimal
from .mark import MarkPlan, mark_rate


class RunState(Enum):
    """Where a marking run has got to."""

    PLANNED = "planned"
    RUNNING = "running"
    CHECKED = "checked"
    ACCEPTED = "accepted"
    REJECTED = "rejected"

    @property
    def is_finished(self) -> bool:
        return self in {RunState.ACCEPTED, RunState.REJECTED}


@dataclass(frozen=True, slots=True)
class QualityCheck:
    """One sample taken off a run to see whether the marking took."""

    day: date
    sampled: int
    marked: int
    tags_detected: int = 0

    def __post_init__(self) -> None:
        object.__setattr__(self, "day", parse_date(self.day))
        if self.sampled < 1:
            raise ValidationError("a check samples fish", field="sampled")
        if self.marked < 0 or self.marked > self.sampled:
            raise ValidationError("more marked than sampled", field="marked")
        if self.tags_detected < 0 or self.tags_detected > self.sampled:
            raise ValidationError("more tags than sampled", field="tags_detected")

    @property
    def mark_share(self) -> Decimal:
        return safe_divide(self.marked, self.sampled, field="sampled")

    @property
    def tag_share(self) -> Decimal:
        return safe_divide(self.tags_detected, self.sampled, field="sampled")

    @property
    def retention(self) -> Decimal:
        """The share of marked fish that still carry a tag."""

        if self.marked == 0:
            return Decimal(0)
        return safe_divide(self.tags_detected, self.marked, field="marked")


@dataclass
class MarkingRun:
    """One trailer, one lot, one day."""

    code: str
    lot: str
    day: date
    plan: MarkPlan
    presented: Decimal
    crew: str
    marked: Decimal = Decimal(0)
    rejected: Decimal = Decimal(0)
    state: RunState = RunState.PLANNED
    checks: list[QualityCheck] = field(default_factory=list)
    note: str = ""

    def __post_init__(self) -> None:
        self.code = normalise_code(self.code, field="run")
        self.lot = normalise_code(self.lot, field="lot")
        self.day = parse_date(self.day)
        self.presented = require_positive(self.presented, field="presented")
        if not self.crew.strip():
            raise ValidationError("a run needs a crew", field="crew")
        self.crew = self.crew.strip()
        if self.plan.lot != self.lot:
            raise ValidationError(f"the plan is for {self.plan.lot}, not {self.lot}", field="plan")

    def start(self) -> None:
        if self.state is not RunState.PLANNED:
            raise StateError(f"run {self.code} is {self.state.value}")
        self.state = RunState.RUNNING

    def finish(self, marked: Number, rejected: Number = 0) -> Decimal:
        """Book what came out of the trailer."""

        if self.state is not RunState.RUNNING:
            raise StateError(f"run {self.code} is {self.state.value} and is not running")
        applied = to_decimal(marked, field="marked")
        thrown = to_decimal(rejected, field="rejected")
        if applied < 0 or thrown < 0:
            raise ValidationError("a count cannot be negative", field="marked")
        if applied + thrown > self.presented:
            raise ValidationError(
                f"{applied + thrown} fish out of a run of {self.presented}", field="marked"
            )
        self.marked = applied
        self.rejected = thrown
        self.state = RunState.CHECKED
        return self.marked

    def check(self, sample: QualityCheck) -> QualityCheck:
        """File a quality check, which has to come after the run."""

        if self.state is RunState.PLANNED:
            raise StateError(f"run {self.code} has not run yet")
        if sample.day < self.day:
            raise ValidationError("a check cannot precede the run", field="day")
        self.checks.append(sample)
        return sample

    def accept(self, *, tolerance: Number = "0.02") -> RunState:
        """Accept or reject the run on its checks against the plan."""

        if self.state is not RunState.CHECKED:
            raise StateError(f"run {self.code} is {self.state.value}")
        if not self.checks:
            raise StateError(f"run {self.code} has no quality check on it")
        allowed = to_decimal(tolerance, field="tolerance")
        if allowed < 0:
            raise ValidationError("a tolerance cannot be negative", field="tolerance")
        share = self.checked_rate()
        self.state = (
            RunState.ACCEPTED if share >= self.plan.target_rate - allowed else RunState.REJECTED
        )
        return self.state

    def checked_rate(self) -> Decimal:
        """The mark rate across every check on the run, weighted by sample size."""

        if not self.checks:
            raise ValidationError("no checks to read", field="checks")
        sampled = sum(check.sampled for check in self.checks)
        marked = sum(check.marked for check in self.checks)
        return safe_divide(marked, sampled, field="checks")

    @property
    def applied_rate(self) -> Decimal:
        """The rate off the run's own counts, before anybody checks it."""

        return mark_rate(self.marked, self.presented) if self.marked else Decimal(0)

    @property
    def shortfall(self) -> Decimal:
        """How many fish still need marking to meet the plan."""

        wanted = self.plan.fish_to_mark(self.presented)
        try:
            achieved = (self.presented * self.checked_rate()).to_integral_value()
        except ValidationError:
            achieved = self.marked
        gap = wanted - achieved
        return gap if gap > 0 else Decimal(0)

    def check_window(self, *, days: int = 14) -> date:
        """The last day a check still says anything about this run."""

        if days < 1:
            raise ValidationError("a check window has days in it", field="days")
        return self.day + timedelta(days=days)

    def is_checked_in_time(self, *, days: int = 14) -> bool:
        limit = self.check_window(days=days)
        return any(check.day <= limit for check in self.checks)


def require_accepted(run: MarkingRun) -> None:
    """Refuse to release a group off a run nobody accepted."""

    if run.state is not RunState.ACCEPTED:
        raise PolicyError(
            f"run {run.code} is {run.state.value} and the group cannot be released",
            rule="marking.unaccepted",
        )
