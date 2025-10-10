"""Marking commands: the tag arithmetic and the quality check.

The tag order command is the one that gets used, because ordering tags is done
months before the trailer arrives and the number has to allow for the ones that
will not take. The check command is what the crew runs on the day, and it gives
the same accept or reject the engine would.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import click

from ..marking.mark import MarkPlan, MarkType, TagCode, mark_rate
from ..marking.run import MarkingRun, QualityCheck
from ..marking.summary import summarise_group, tags_needed
from .main import Context, guarded, main, pass_context
from .options import format_option
from .output import echo, echo_pairs, parse_format


def _plan(lot: str, marks: tuple[str, ...], tag: str, rate: str) -> MarkPlan:
    chosen = tuple(MarkType(entry) for entry in marks) or (MarkType.ADIPOSE_CLIP,)
    return MarkPlan(
        lot=lot,
        marks=chosen,
        tag_code=TagCode(tag) if tag else None,
        target_rate=Decimal(rate),
    )


@main.group()
def mark() -> None:
    """Work out the marking and check what came off the trailer."""


@mark.command("order")
@click.option("--lot", "lot_code", required=True, help="The lot to mark.")
@click.option("--fish", required=True, help="How many fish are in it.")
@click.option(
    "--type",
    "marks",
    multiple=True,
    type=click.Choice([entry.value for entry in MarkType]),
    help="A mark to apply. Repeat for more than one.",
)
@click.option("--tag", default="", help="The tag code, if there is one.")
@click.option("--rate", default="1.0", show_default=True, help="Share of the lot to mark.")
@click.option("--retention", default="0.95", show_default=True, help="Expected tag retention.")
@format_option
@pass_context
@guarded
def order(
    context: Context,
    lot_code: str,
    fish: str,
    marks: tuple[str, ...],
    tag: str,
    rate: str,
    retention: str,
    form: str,
) -> None:
    """Say how many fish to mark and how many tags to order."""

    plan = _plan(lot_code, marks, tag, rate)
    to_mark = plan.fish_to_mark(fish)
    echo_pairs(
        [
            ("lot", plan.lot),
            ("marks", ", ".join(entry.value for entry in plan.marks)),
            ("tag code", str(plan.tag_code) if plan.tag_code else ""),
            ("fish", Decimal(fish)),
            ("to mark", to_mark),
            ("tags to order", tags_needed(plan, fish, expected_retention=retention)),
            ("double index", plan.is_visible and plan.needs_a_code),
        ],
        parse_format(form),
        places=context.places,
    )


@mark.command("check")
@click.option("--lot", "lot_code", required=True, help="The lot that was marked.")
@click.option("--presented", required=True, help="How many went through the trailer.")
@click.option("--marked", required=True, help="How many came out marked.")
@click.option("--sampled", required=True, help="How many were checked afterwards.")
@click.option("--found", required=True, help="How many of those carried the mark.")
@click.option("--tags", default="0", show_default=True, help="How many carried a tag.")
@click.option("--rate", default="1.0", show_default=True, help="The rate the plan wanted.")
@format_option
@pass_context
@guarded
def check(
    context: Context,
    lot_code: str,
    presented: str,
    marked: str,
    sampled: str,
    found: str,
    tags: str,
    rate: str,
    form: str,
) -> None:
    """Accept or reject a run on its quality check."""

    plan = _plan(lot_code, (MarkType.ADIPOSE_CLIP.value,), "", rate)
    marking = MarkingRun(
        code="MR-1",
        lot=lot_code,
        day=date(2000, 1, 1),
        plan=plan,
        presented=Decimal(presented),
        crew="command line",
    )
    marking.start()
    marking.finish(Decimal(marked))
    marking.check(
        QualityCheck(
            day=date(2000, 1, 2),
            sampled=int(sampled),
            marked=int(found),
            tags_detected=int(tags),
        )
    )
    state = marking.accept()
    echo_pairs(
        [
            ("lot", marking.lot),
            ("applied rate", marking.applied_rate.quantize(Decimal("0.0001"))),
            ("checked rate", marking.checked_rate().quantize(Decimal("0.0001"))),
            ("shortfall", marking.shortfall),
            ("state", state.value),
        ],
        parse_format(form),
        places=context.places,
    )


@mark.command("group")
@click.option("--lot", "lot_code", required=True, help="The release group's lot.")
@click.option(
    "--run",
    "runs",
    multiple=True,
    help="presented:marked:sampled:found:tags:days_after",
)
@click.option("--rate", default="1.0", show_default=True, help="The rate the plan wanted.")
@format_option
@pass_context
@guarded
def group(context: Context, lot_code: str, runs: tuple[str, ...], rate: str, form: str) -> None:
    """Add several runs up into the numbers on the release report."""

    plan = _plan(lot_code, (MarkType.ADIPOSE_CLIP.value,), "", rate)
    built = []
    for index, raw in enumerate(runs, start=1):
        parts = raw.split(":")
        if len(parts) != 6:
            raise click.ClickException(
                f"{raw!r} is not presented:marked:sampled:found:tags:days_after"
            )
        marking = MarkingRun(
            code=f"MR-{index:03d}",
            lot=lot_code,
            day=date(2025, 1, 1),
            plan=plan,
            presented=Decimal(parts[0]),
            crew="command line",
        )
        marking.start()
        marking.finish(Decimal(parts[1]))
        marking.check(
            QualityCheck(
                day=date(2025, 1, 1 + int(parts[5])),
                sampled=int(parts[2]),
                marked=int(parts[3]),
                tags_detected=int(parts[4]),
            )
        )
        marking.accept()
        built.append(marking)
    summary = summarise_group(plan, built)
    echo(
        ["runs", "accepted", "presented", "marked", "rate", "retention", "effective"],
        [
            [
                Decimal(summary.runs),
                Decimal(summary.accepted_runs),
                summary.presented,
                summary.marked,
                summary.checked_rate,
                summary.retention,
                summary.effective_rate,
            ]
        ],
        parse_format(form),
        places=4,
    )
    context.say(summary.line())


@mark.command("rate")
@click.option("--marked", required=True, help="How many were marked.")
@click.option("--population", required=True, help="How many there are.")
@format_option
@pass_context
@guarded
def rate_command(context: Context, marked: str, population: str, form: str) -> None:
    """Work out a mark rate."""

    echo_pairs(
        [
            ("marked", Decimal(marked)),
            ("population", Decimal(population)),
            ("rate", mark_rate(marked, population).quantize(Decimal("0.0001"))),
        ],
        parse_format(form),
        places=context.places,
    )
