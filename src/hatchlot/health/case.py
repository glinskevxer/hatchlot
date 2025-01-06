"""A health case: what was found, what was done, and whether it worked.

A case opens on an examination and does not close because somebody treated the
lot. It closes on a follow-up examination that shows the thing has gone. That
distinction is the entire discipline: a station that closes cases on treatment
never finds out that half its treatments do nothing.

While a case is open the lot is held, which is what stops treated fish going out
on a truck on a Friday afternoon.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from enum import Enum

from ..calendar import parse_date
from ..errors import StateError, ValidationError
from ..identifiers import normalise_code
from ..numeric import Number, to_decimal
from .exam import Examination, Finding
from .treatment import Treatment


class CaseState(Enum):
    """Where a case is."""

    OPEN = "open"
    TREATING = "treating"
    WATCHING = "watching"
    CLOSED = "closed"
    ESCALATED = "escalated"

    @property
    def holds_the_lot(self) -> bool:
        return self not in {CaseState.CLOSED}


class Outcome(Enum):
    """How a case ended."""

    RESOLVED = "resolved"
    PERSISTED = "persisted"
    LOT_LOST = "lot_lost"
    NOT_A_CASE = "not_a_case"


@dataclass(frozen=True, slots=True)
class CaseEvent:
    """One thing that happened on a case."""

    day: date
    kind: str
    detail: str
    by: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "day", parse_date(self.day))
        for name in ("kind", "detail", "by"):
            if not getattr(self, name).strip():
                raise ValidationError(f"a case event needs a {name}", field=name)
            object.__setattr__(self, name, getattr(self, name).strip())


@dataclass
class Case:
    """One health case on one lot."""

    code: str
    lot: str
    finding: Finding
    opened_on: date
    opened_by: str
    state: CaseState = CaseState.OPEN
    diagnosis: str = ""
    outcome: Outcome | None = None
    opening_prevalence: Decimal = Decimal(0)
    closing_prevalence: Decimal | None = None
    events: list[CaseEvent] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.code = normalise_code(self.code, field="case")
        self.lot = normalise_code(self.lot, field="lot")
        if not isinstance(self.finding, Finding):
            raise ValidationError(f"{self.finding!r} is not a finding", field="finding")
        self.opened_on = parse_date(self.opened_on)
        if not self.opened_by.strip():
            raise ValidationError("a case needs whoever opened it", field="opened_by")
        self.opened_by = self.opened_by.strip()

    def _log(self, day: object, kind: str, detail: str, by: str) -> CaseEvent:
        event = CaseEvent(day=parse_date(day), kind=kind, detail=detail, by=by)
        if self.events and event.day < self.events[-1].day:
            raise ValidationError("a case event cannot precede the one before", field="day")
        self.events.append(event)
        return event

    def diagnose(self, day: object, diagnosis: str, by: str) -> CaseEvent:
        if self.state is CaseState.CLOSED:
            raise StateError(f"case {self.code} is closed")
        if not diagnosis.strip():
            raise ValidationError("a diagnosis needs words in it", field="diagnosis")
        self.diagnosis = diagnosis.strip()
        return self._log(day, "diagnosis", self.diagnosis, by)

    def treat(self, day: object, treatment: Treatment, by: str) -> CaseEvent:
        """Record a treatment, which moves the case on but does not end it."""

        if self.state is CaseState.CLOSED:
            raise StateError(f"case {self.code} is closed")
        treatment.check()
        self.state = CaseState.TREATING
        return self._log(
            day,
            "treatment",
            f"{treatment.chemical.value} {treatment.concentration_ppm} ppm "
            f"for {treatment.minutes} minutes",
            by,
        )

    def watch(self, day: object, by: str, note: str = "waiting on a follow up") -> CaseEvent:
        if self.state is CaseState.CLOSED:
            raise StateError(f"case {self.code} is closed")
        self.state = CaseState.WATCHING
        return self._log(day, "watch", note, by)

    def escalate(self, day: object, by: str, reason: str) -> CaseEvent:
        """Hand the case to somebody else, which a vet referral is."""

        if self.state is CaseState.CLOSED:
            raise StateError(f"case {self.code} is closed")
        if not reason.strip():
            raise ValidationError("an escalation needs a reason", field="reason")
        self.state = CaseState.ESCALATED
        return self._log(day, "escalation", reason, by)

    def close_on(
        self,
        day: object,
        follow_up: Examination,
        by: str,
        *,
        cleared_below: Number = "0.05",
    ) -> Outcome:
        """Close the case on a follow-up examination rather than on a treatment."""

        if self.state is CaseState.CLOSED:
            raise StateError(f"case {self.code} is closed")
        if follow_up.lot != self.lot:
            raise ValidationError(
                f"that examination is of {follow_up.lot}, not {self.lot}", field="follow_up"
            )
        if follow_up.day < self.opened_on:
            raise ValidationError("the follow up is before the case opened", field="follow_up")
        threshold = to_decimal(cleared_below, field="cleared_below")
        prevalence = follow_up.prevalence(self.finding)
        self.closing_prevalence = prevalence
        self.outcome = Outcome.RESOLVED if prevalence < threshold else Outcome.PERSISTED
        self.state = CaseState.CLOSED
        self._log(day, "closed", self.outcome.value, by)
        return self.outcome

    def abandon(self, day: object, by: str, outcome: Outcome) -> Outcome:
        """Close a case without a follow up, which only two outcomes allow."""

        if outcome not in {Outcome.LOT_LOST, Outcome.NOT_A_CASE}:
            raise ValidationError(
                "a case only closes without a follow up when there is nothing to examine",
                field="outcome",
            )
        if self.state is CaseState.CLOSED:
            raise StateError(f"case {self.code} is closed")
        self.outcome = outcome
        self.state = CaseState.CLOSED
        self._log(day, "closed", outcome.value, by)
        return outcome

    @property
    def is_open(self) -> bool:
        return self.state is not CaseState.CLOSED

    @property
    def holds_lot(self) -> bool:
        return self.state.holds_the_lot

    def duration(self, as_of: object) -> int:
        day = parse_date(as_of)
        if day < self.opened_on:
            raise ValidationError("that is before the case opened", field="as_of")
        return (day - self.opened_on).days

    def treatments_given(self) -> int:
        return len([event for event in self.events if event.kind == "treatment"])


def open_case(code: str, examination: Examination, finding: Finding, by: str) -> Case:
    """Open a case off an examination, taking the prevalence with it."""

    prevalence = examination.prevalence(finding)
    if prevalence == 0:
        raise ValidationError(f"that examination found no {finding.value}", field="finding")
    return Case(
        code=code,
        lot=examination.lot,
        finding=finding,
        opened_on=examination.day,
        opened_by=by,
        opening_prevalence=prevalence,
    )


def improvement(case: Case) -> Decimal | None:
    """How far the prevalence fell, as a share of where it started."""

    if case.closing_prevalence is None or case.opening_prevalence == 0:
        return None
    return (case.opening_prevalence - case.closing_prevalence) / case.opening_prevalence
