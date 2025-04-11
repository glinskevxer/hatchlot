"""The permit itself, and the report it makes you file.

A permit is a set of limits, a set of outfalls they apply at, a sampling
frequency, and a term. All four matter to whether a station is in compliance,
and the one that is forgotten is the term: a limit that came into force in April
does not apply to a March sample, and a permit that has lapsed does not make the
station compliant, it makes it unpermitted.

The report is a rollup per limit rather than per sample, because that is the
form the agency's paperwork takes and building it anywhere else means building
it twice.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from ..calendar import DateRange, parse_date
from ..errors import ValidationError
from ..identifiers import normalise_code
from ..numeric import safe_divide
from .limits import Basis, Limit, Parameter
from .monitoring import Exceedance, MonitoringRecord


@dataclass
class Permit:
    """One discharge permit, with its limits and its term."""

    code: str
    holder: str
    term: DateRange
    outfalls: tuple[str, ...]
    limits: list[Limit] = field(default_factory=list)
    sampling_per_month: int = 4

    def __post_init__(self) -> None:
        self.code = normalise_code(self.code, field="permit")
        if not self.holder.strip():
            raise ValidationError("a permit needs a holder", field="holder")
        self.holder = self.holder.strip()
        if not self.outfalls:
            raise ValidationError("a permit covers an outfall", field="outfalls")
        self.outfalls = tuple(normalise_code(code, field="outfalls") for code in self.outfalls)
        if len(set(self.outfalls)) != len(self.outfalls):
            raise ValidationError("the same outfall twice", field="outfalls")
        if self.sampling_per_month < 1:
            raise ValidationError("a frequency is at least one", field="sampling_per_month")

    def add_limit(self, limit: Limit) -> Limit:
        """Put a limit on the permit, refusing a second one of the same kind."""

        for existing in self.limits:
            if existing.parameter is limit.parameter and existing.basis is limit.basis:
                raise ValidationError(
                    f"the permit already limits {limit.parameter.value} on {limit.basis.value}",
                    field="limit",
                )
        self.limits.append(limit)
        return limit

    def is_in_force(self, day: object) -> bool:
        return parse_date(day) in self.term

    def covers(self, outfall: str) -> bool:
        return normalise_code(outfall, field="outfall") in self.outfalls

    def limits_for(self, parameter: Parameter) -> tuple[Limit, ...]:
        return tuple(limit for limit in self.limits if limit.parameter is parameter)

    def parameters(self) -> tuple[Parameter, ...]:
        return tuple(sorted({limit.parameter for limit in self.limits}, key=lambda p: p.value))

    def expires_in(self, as_of: object) -> int:
        """Days left on the term, negative once it has lapsed."""

        return (self.term.end - parse_date(as_of)).days


@dataclass(frozen=True, slots=True)
class LimitResult:
    """One limit's line on a report."""

    limit: Limit
    samples: int
    average: Decimal | None
    maximum: Decimal | None
    exceedances: tuple[Exceedance, ...]

    @property
    def is_compliant(self) -> bool:
        if self.exceedances:
            return False
        if self.limit.basis is Basis.CONCENTRATION and self.average is not None:
            return self.average <= self.limit.value
        return True

    @property
    def worst_share(self) -> Decimal:
        if self.maximum is None:
            return Decimal(0)
        return safe_divide(self.maximum, self.limit.value, field="limit")


@dataclass(frozen=True, slots=True)
class PeriodReport:
    """One reporting period, per limit, ready to be typed onto a form."""

    permit: str
    window: DateRange
    results: tuple[LimitResult, ...]
    frequency_met: bool
    in_force: bool

    @property
    def is_compliant(self) -> bool:
        return (
            self.in_force
            and self.frequency_met
            and all(result.is_compliant for result in self.results)
        )

    @property
    def failing(self) -> tuple[LimitResult, ...]:
        return tuple(result for result in self.results if not result.is_compliant)

    def line(self) -> str:
        state = "compliant" if self.is_compliant else "not compliant"
        return (
            f"{self.permit} {self.window}: {len(self.results)} limits, "
            f"{len(self.failing)} failing, {state}"
        )


def build_report(permit: Permit, record: MonitoringRecord, window: DateRange) -> PeriodReport:
    """Roll a monitoring record up into one period's report."""

    if not permit.limits:
        raise ValidationError("the permit has no limits to report against", field="permit")
    results: list[LimitResult] = []
    frequency = True
    for limit in permit.limits:
        readings = record.for_parameter(limit.parameter, window)
        values = [reading.sample.value_for(limit) for reading in readings]
        results.append(
            LimitResult(
                limit=limit,
                samples=len(readings),
                average=(sum(values, Decimal(0)) / Decimal(len(values))) if values else None,
                maximum=max(values) if values else None,
                exceedances=record.daily_exceedances(limit, window),
            )
        )
        if not record.is_frequency_met(
            limit.parameter, window, per_month=permit.sampling_per_month
        ):
            frequency = False
    return PeriodReport(
        permit=permit.code,
        window=window,
        results=tuple(results),
        frequency_met=frequency,
        in_force=permit.is_in_force(window.start) and permit.is_in_force(window.end),
    )


def periods(term: DateRange, *, months: int = 1) -> tuple[DateRange, ...]:
    """Split a term into reporting periods of whole months."""

    if months < 1:
        raise ValidationError("a period is at least a month", field="months")
    from ..calendar import add_months

    out: list[DateRange] = []
    start: date = term.start
    while start <= term.end:
        end = add_months(start, months)
        last = min(end, term.end)
        if last < start:
            break
        out.append(DateRange(start, last))
        if last == term.end:
            break
        start = last
    return tuple(out)
