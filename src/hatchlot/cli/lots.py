"""Lot commands: what is in the units, and what happens to it.

The commands here write to two places at once, which is the point of them. A
sample changes the lot's mean weight; a mortality changes the population and
writes a ledger entry. Doing either of those by hand in two places is how the
ledger and the lot stop agreeing, and the reconcile command exists because it
happens anyway.
"""

from __future__ import annotations

from decimal import Decimal

import click

from ..calendar import parse_date
from ..identifiers import LotCode
from ..quantities.base import Quantity
from ..rearing.ledger import EntryKind, LedgerEntry
from ..rearing.lot import RearingLot
from ..store.lots import load_lot, save_entry, save_lot
from ..store.session import open_session
from .main import Context, guard, main, pass_context
from .options import format_option
from .output import count_line, echo, echo_pairs, parse_format


@main.group()
def lot() -> None:
    """Work on the rearing lots."""


@lot.command("pond")
@click.option("--code", required=True, help="The lot code, such as 2024-CHK-01.")
@click.option("--unit", required=True, help="The unit it goes into.")
@click.option("--day", required=True, help="The day it was ponded.")
@click.option("--fish", required=True, help="How many fish went in.")
@click.option("--weight", required=True, help="Mean weight in grams.")
@click.option("--by", "entered_by", default="hatchery", show_default=True)
@pass_context
def pond(
    context: Context,
    code: str,
    unit: str,
    day: str,
    fish: str,
    weight: str,
    entered_by: str,
) -> None:
    """Put a lot into a unit and open its ledger."""

    def run() -> None:
        record = RearingLot(
            code=LotCode.parse(code),
            container=unit,
            ponded_on=parse_date(day),
            population=Decimal(fish),
            mean_weight=Quantity(weight, "g"),
        )
        with open_session(context.database) as session:
            save_lot(session.connection, record)
            save_entry(
                session.connection,
                LedgerEntry(
                    day=day,
                    lot=str(record.code),
                    kind=EntryKind.PONDED,
                    count=record.population,
                    entered_by=entered_by,
                    counterparty=record.container,
                ),
            )
            context.say(f"lot {record.code} ponded into {record.container}")

    guard(run)


@lot.command("list")
@format_option
@click.option("--all", "include_closed", is_flag=True, help="Include the closed lots.")
@pass_context
def list_lots(context: Context, form: str, include_closed: bool) -> None:
    """List the lots the station is holding."""

    def run() -> None:
        with open_session(context.database) as session:
            found = session.lots(live_only=not include_closed)
            echo(
                ["lot", "unit", "fish", "mean weight", "biomass", "state"],
                [
                    [
                        str(entry.code),
                        entry.container,
                        entry.population,
                        entry.mean_weight,
                        entry.biomass,
                        entry.state.value,
                    ]
                    for entry in found
                ],
                parse_format(form),
                places=context.places,
            )
            context.say(count_line("lot", len(found)))

    guard(run)


@lot.command("show")
@click.argument("code")
@format_option
@pass_context
def show(context: Context, code: str, form: str) -> None:
    """Print one lot, and how far it is off its own ledger."""

    def run() -> None:
        with open_session(context.database) as session:
            record = load_lot(session.connection, code)
            balance = session.ledger(lot=str(record.code)).balance(str(record.code))
            echo_pairs(
                [
                    ("lot", str(record.code)),
                    ("unit", record.container),
                    ("fish", record.population),
                    ("ledger", balance.closing),
                    ("difference", record.population - balance.closing),
                    ("mean weight", record.mean_weight.rounded(context.places)),
                    ("biomass", record.biomass.rounded(context.places)),
                    ("fish per pound", record.fish_per_pound.quantize(Decimal("0.1"))),
                    ("state", record.state.value),
                ],
                parse_format(form),
                places=context.places,
            )

    guard(run)


@lot.command("sample")
@click.argument("code")
@click.option("--weight", required=True, help="The new mean weight in grams.")
@pass_context
def sample(context: Context, code: str, weight: str) -> None:
    """Record a new mean weight off a sample."""

    def run() -> None:
        with open_session(context.database) as session:
            record = load_lot(session.connection, code)
            before = record.mean_weight
            record.resize(Quantity(weight, "g"))
            save_lot(session.connection, record)
            context.say(
                f"{record.code} {before.rounded(context.places)} to "
                f"{record.mean_weight.rounded(context.places)}"
            )

    guard(run)


@lot.command("mortality")
@click.argument("code")
@click.option("--day", required=True, help="The day they were picked up.")
@click.option("--count", required=True, help="How many died.")
@click.option("--reason", required=True, help="Why, in a few words.")
@click.option("--by", "entered_by", default="hatchery", show_default=True)
@pass_context
def mortality(
    context: Context, code: str, day: str, count: str, reason: str, entered_by: str
) -> None:
    """Take mortality off a lot and write it to the ledger."""

    def run() -> None:
        with open_session(context.database) as session:
            record = load_lot(session.connection, code)
            record.remove(Decimal(count))
            save_lot(session.connection, record)
            save_entry(
                session.connection,
                LedgerEntry(
                    day=day,
                    lot=str(record.code),
                    kind=EntryKind.MORTALITY,
                    count=Decimal(count),
                    entered_by=entered_by,
                    reason=reason,
                ),
            )
            context.say(f"{record.code} now {record.population:.0f} fish")

    guard(run)


@lot.command("move")
@click.argument("code")
@click.option("--to", "destination", required=True, help="The unit it goes to.")
@pass_context
def move(context: Context, code: str, destination: str) -> None:
    """Move a lot into another unit."""

    def run() -> None:
        with open_session(context.database) as session:
            container = session.containers().get(destination)
            container.check_available()
            record = load_lot(session.connection, code)
            was = record.container
            record.move_to(container.code)
            save_lot(session.connection, record)
            context.say(f"{record.code} moved from {was} to {record.container}")

    guard(run)


@lot.command("reconcile")
@format_option
@pass_context
def reconcile(context: Context, form: str) -> None:
    """Show every lot whose record and ledger disagree."""

    def run() -> None:
        with open_session(context.database) as session:
            rows = []
            for record in session.lots():
                balance = session.ledger(lot=str(record.code)).balance(str(record.code))
                difference = record.population - balance.closing
                if difference != 0:
                    rows.append([str(record.code), record.population, balance.closing, difference])
            echo(["lot", "record", "ledger", "difference"], rows, parse_format(form))
            context.say(count_line("disagreement", len(rows)))

    guard(run)
