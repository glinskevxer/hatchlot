"""What a release group ends up carrying, once the runs are all in.

A group is usually marked over several days on several trailers, and the number
that goes on the release report is not any one run's rate. It is the marked fish
over the fish released, worked out across every run, and it has to be reported
with the tag retention alongside it because a tag that fell out before release
is a fish nobody will ever identify.

Retention is estimated off the quality checks rather than assumed, and a group
whose checks were all taken on the day of marking has no retention estimate at
all. Saying so is better than reporting the day-one number as if it meant
something.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal

from ..errors import ValidationError
from ..numeric import Number, require_positive, safe_divide, to_decimal
from .mark import MarkPlan, TagCode
from .run import MarkingRun, RunState


@dataclass(frozen=True, slots=True)
class GroupMarking:
    """The marking of one release group, across every run on it."""

    lot: str
    tag_code: TagCode | None
    runs: int
    accepted_runs: int
    presented: Decimal
    marked: Decimal
    checked_rate: Decimal
    retention: Decimal | None
    target_rate: Decimal

    @property
    def meets_target(self) -> bool:
        return self.checked_rate >= self.target_rate

    @property
    def shortfall(self) -> Decimal:
        """How many fish still need marking, judged on the checked rate.

        The run's own count is what the crew thought it did. The checked rate is
        what a sample says it did, and that is the one the shortfall comes off.
        """

        gap = (self.presented * self.target_rate) - (self.presented * self.checked_rate)
        return gap if gap > 0 else Decimal(0)

    @property
    def effective_rate(self) -> Decimal:
        """The share still carrying a tag at release, which is the useful number."""

        if self.retention is None:
            return self.checked_rate
        return self.checked_rate * self.retention

    def line(self) -> str:
        retention = f"{self.retention:.1%}" if self.retention is not None else "unknown"
        return (
            f"{self.lot}: {self.marked:.0f} of {self.presented:.0f} marked, "
            f"rate {self.checked_rate:.1%}, retention {retention}"
        )


def summarise_group(
    plan: MarkPlan, runs: list[MarkingRun], *, retention_after_days: int = 7
) -> GroupMarking:
    """Add a group's runs up into the numbers that go on the release report."""

    if not runs:
        raise ValidationError("a group needs at least one run", field="runs")
    for run in runs:
        if run.lot != plan.lot:
            raise ValidationError(f"run {run.code} is for {run.lot}, not {plan.lot}", field="runs")
    presented = sum((run.presented for run in runs), Decimal(0))
    marked = sum((run.marked for run in runs), Decimal(0))
    sampled = sum(check.sampled for run in runs for check in run.checks)
    checked = sum(check.marked for run in runs for check in run.checks)
    rate = (
        safe_divide(checked, sampled, field="checks")
        if sampled
        else safe_divide(marked, presented, field="presented")
    )
    late = [
        check
        for run in runs
        for check in run.checks
        if check.day >= run.day + timedelta(days=retention_after_days)
    ]
    retention: Decimal | None = None
    if late:
        marked_late = sum(check.marked for check in late)
        tags_late = sum(check.tags_detected for check in late)
        retention = (
            safe_divide(tags_late, marked_late, field="checks") if marked_late else Decimal(0)
        )
    return GroupMarking(
        lot=plan.lot,
        tag_code=plan.tag_code,
        runs=len(runs),
        accepted_runs=len([run for run in runs if run.state is RunState.ACCEPTED]),
        presented=presented,
        marked=marked,
        checked_rate=rate,
        retention=retention,
        target_rate=plan.target_rate,
    )


def expanded_tags(group: GroupMarking, released: Number) -> Decimal:
    """How many tagged fish a release actually puts in the water."""

    count = require_positive(released, field="released")
    return count * group.effective_rate


def tags_needed(
    plan: MarkPlan, population: Number, *, expected_retention: Number = "0.95"
) -> Decimal:
    """How many tags to order for a group, allowing for the ones that fail."""

    retention = to_decimal(expected_retention, field="expected_retention")
    if not 0 < retention <= 1:
        raise ValidationError("that is not a retention share", field="expected_retention")
    return (plan.fish_to_mark(population) / retention).to_integral_value(rounding="ROUND_CEILING")


def unmarked_remaining(group: GroupMarking) -> Decimal:
    """Fish in the group that are not carrying the mark."""

    left = group.presented - group.marked
    return left if left > 0 else Decimal(0)
