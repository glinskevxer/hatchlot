"""The fish health picture, over a window and across the station.

Three counts and one judgement. How many cases are open, how many lots are held
because of them, how long the open ones have been open, and whether the pattern
across lots looks like one problem or several. That last one is a guess and it
is labelled as a guess, but a station with the same finding open on four units at
once has a water problem rather than four fish problems.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from ..calendar import DateRange, parse_date
from ..errors import ValidationError
from ..numeric import Number, safe_divide, to_decimal
from .case import Case, CaseState
from .exam import Examination, Finding


@dataclass(frozen=True, slots=True)
class HealthSummary:
    """Where the station's fish health stands."""

    window: DateRange
    examinations: int
    cases_opened: int
    cases_closed: int
    open_cases: tuple[str, ...]
    held_lots: tuple[str, ...]
    oldest_open_days: int
    common_finding: Finding | None
    resolved_share: Decimal

    @property
    def looks_like_one_problem(self) -> bool:
        """Whether the open cases share a finding, which points at the water."""

        return self.common_finding is not None and len(self.open_cases) >= 3

    def line(self) -> str:
        finding = self.common_finding.value if self.common_finding else "none"
        return (
            f"{self.window}: {self.examinations} exams, {len(self.open_cases)} cases open, "
            f"{len(self.held_lots)} lots held, most common {finding}"
        )


def summarise_health(
    cases: list[Case],
    examinations: list[Examination],
    window: DateRange,
    as_of: object,
) -> HealthSummary:
    """Pull the health picture together as of a day."""

    when = parse_date(as_of)
    inside = [exam for exam in examinations if exam.day in window]
    opened = [case for case in cases if case.opened_on in window]
    closed = [
        case
        for case in cases
        if case.state is CaseState.CLOSED and case.events and case.events[-1].day in window
    ]
    open_cases = [case for case in cases if case.is_open]
    held = sorted({case.lot for case in cases if case.holds_lot})
    ages = [case.duration(when) for case in open_cases if case.opened_on <= when]
    counts: dict[Finding, int] = {}
    for case in open_cases:
        counts[case.finding] = counts.get(case.finding, 0) + 1
    resolved = [
        case for case in closed if case.outcome is not None and case.outcome.value == "resolved"
    ]
    return HealthSummary(
        window=window,
        examinations=len(inside),
        cases_opened=len(opened),
        cases_closed=len(closed),
        open_cases=tuple(sorted(case.code for case in open_cases)),
        held_lots=tuple(held),
        oldest_open_days=max(ages) if ages else 0,
        common_finding=max(counts, key=lambda finding: counts[finding]) if counts else None,
        resolved_share=safe_divide(len(resolved), len(closed), field="closed")
        if closed
        else Decimal(0),
    )


def stale_cases(cases: list[Case], as_of: object, *, days: int = 30) -> tuple[Case, ...]:
    """Open cases that have been open too long to still be watched."""

    if days < 1:
        raise ValidationError("a staleness window has days in it", field="days")
    when = parse_date(as_of)
    return tuple(
        case
        for case in cases
        if case.is_open and case.opened_on <= when and case.duration(when) >= days
    )


def treatment_load(cases: list[Case]) -> int:
    """How many treatments the station has given across all its cases."""

    return sum(case.treatments_given() for case in cases)


def is_outbreak(
    cases: list[Case], finding: Finding, *, lots: int = 3, share: Number = "0.5"
) -> bool:
    """Whether one finding is open on enough of the station to call it an outbreak."""

    open_cases = [case for case in cases if case.is_open]
    if len(open_cases) < lots:
        return False
    matching = [case for case in open_cases if case.finding is finding]
    if len(matching) < lots:
        return False
    threshold = to_decimal(share, field="share")
    if not 0 < threshold <= 1:
        raise ValidationError("that is not a share of the open cases", field="share")
    return Decimal(len(matching)) / Decimal(len(open_cases)) >= threshold
