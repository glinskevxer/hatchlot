"""The compliance report: everything the station could be asked to prove.

A hatchery is audited on four separate things by four separate people, and they
are all in here because a station that keeps them in four places finds out about
the fourth one on the day of the audit. Discharge against the permit. Fish health
holds. Marking runs somebody accepted. Drug withdrawals that have not cleared.

Each finding carries the rule it came from, so the report can be sorted by who
is going to ask about it.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum

from ..calendar import DateRange
from ..errors import ValidationError
from ..health.case import Case
from ..marking.run import MarkingRun, RunState
from ..numeric import safe_divide
from ..permits.permit import PeriodReport
from .tables import Align, Column, bullet_list, heading, join_sections, render_table


class Area(Enum):
    """Who asks about a finding."""

    DISCHARGE = "discharge"
    FISH_HEALTH = "fish_health"
    MARKING = "marking"
    WITHDRAWAL = "withdrawal"

    @property
    def is_regulatory(self) -> bool:
        """The two an outside body writes to the station about."""

        return self in {Area.DISCHARGE, Area.WITHDRAWAL}


@dataclass(frozen=True, slots=True)
class Finding:
    """One thing that is not right."""

    area: Area
    subject: str
    detail: str

    def __post_init__(self) -> None:
        if not isinstance(self.area, Area):
            raise ValidationError(f"{self.area!r} is not an area", field="area")
        for name in ("subject", "detail"):
            if not getattr(self, name).strip():
                raise ValidationError(f"a finding needs a {name}", field=name)
            object.__setattr__(self, name, getattr(self, name).strip())

    @property
    def line(self) -> str:
        return f"[{self.area.value}] {self.subject}: {self.detail}"


@dataclass(frozen=True, slots=True)
class ComplianceReport:
    """Everything the station would have to answer for, over a window."""

    window: DateRange
    findings: tuple[Finding, ...]
    checked: int

    @property
    def is_clean(self) -> bool:
        return not self.findings

    @property
    def regulatory(self) -> tuple[Finding, ...]:
        return tuple(entry for entry in self.findings if entry.area.is_regulatory)

    def for_area(self, area: Area) -> tuple[Finding, ...]:
        return tuple(entry for entry in self.findings if entry.area is area)

    @property
    def clean_share(self) -> Decimal:
        if self.checked == 0:
            return Decimal(0)
        return safe_divide(self.checked - len(self.findings), self.checked, field="checked")

    def line(self) -> str:
        state = "nothing outstanding" if self.is_clean else f"{len(self.findings)} findings"
        return f"{self.window}: {self.checked} checks, {state}"


def from_discharge(reports: list[PeriodReport]) -> tuple[Finding, ...]:
    """Findings off the permit reports."""

    found: list[Finding] = []
    for report in reports:
        if not report.in_force:
            found.append(
                Finding(
                    area=Area.DISCHARGE,
                    subject=report.permit,
                    detail="the permit was not in force over this period",
                )
            )
        if not report.frequency_met:
            found.append(
                Finding(
                    area=Area.DISCHARGE,
                    subject=report.permit,
                    detail="the sampling frequency was not met",
                )
            )
        for result in report.failing:
            found.append(
                Finding(
                    area=Area.DISCHARGE,
                    subject=report.permit,
                    detail=f"{result.limit.description} was exceeded",
                )
            )
    return tuple(found)


def from_health(cases: list[Case]) -> tuple[Finding, ...]:
    """Findings off the open health cases."""

    return tuple(
        Finding(
            area=Area.FISH_HEALTH,
            subject=case.lot,
            detail=f"case {case.code} is {case.state.value} on {case.finding.value}",
        )
        for case in cases
        if case.is_open
    )


def from_marking(runs: list[MarkingRun]) -> tuple[Finding, ...]:
    """Findings off the marking runs."""

    found: list[Finding] = []
    for run in runs:
        if run.state is RunState.REJECTED:
            found.append(
                Finding(
                    area=Area.MARKING,
                    subject=run.lot,
                    detail=f"run {run.code} was rejected and has not been redone",
                )
            )
        elif run.state is not RunState.ACCEPTED:
            found.append(
                Finding(
                    area=Area.MARKING,
                    subject=run.lot,
                    detail=f"run {run.code} is {run.state.value} and not accepted",
                )
            )
    return tuple(found)


def from_withdrawals(holds: dict[str, Decimal]) -> tuple[Finding, ...]:
    """Findings off the drug withdrawals still outstanding."""

    return tuple(
        Finding(
            area=Area.WITHDRAWAL,
            subject=lot,
            detail=f"{remaining} degree days still to run",
        )
        for lot, remaining in sorted(holds.items())
        if remaining > 0
    )


def build_compliance_report(
    window: DateRange,
    *,
    discharge: list[PeriodReport] | None = None,
    cases: list[Case] | None = None,
    runs: list[MarkingRun] | None = None,
    withdrawals: dict[str, Decimal] | None = None,
) -> ComplianceReport:
    """Gather every area's findings into one report."""

    findings: list[Finding] = []
    checked = 0
    if discharge:
        findings.extend(from_discharge(discharge))
        checked += len(discharge)
    if cases:
        findings.extend(from_health(cases))
        checked += len(cases)
    if runs:
        findings.extend(from_marking(runs))
        checked += len(runs)
    if withdrawals:
        findings.extend(from_withdrawals(withdrawals))
        checked += len(withdrawals)
    return ComplianceReport(window=window, findings=tuple(findings), checked=checked)


def render_compliance(report: ComplianceReport) -> str:
    """Print the compliance report."""

    columns = [
        Column(heading="area"),
        Column(heading="subject"),
        Column(heading="finding"),
        Column(heading="regulatory", align=Align.RIGHT),
    ]
    rows = [
        [entry.area.value, entry.subject, entry.detail, entry.area.is_regulatory]
        for entry in report.findings
    ]
    sections = [heading(f"Compliance {report.window}"), report.line()]
    if report.findings:
        sections.append(render_table(columns, rows))
        if report.regulatory:
            sections.append(heading("Regulatory", underline="-"))
            sections.append(bullet_list([entry.line for entry in report.regulatory]))
    return join_sections(sections)
