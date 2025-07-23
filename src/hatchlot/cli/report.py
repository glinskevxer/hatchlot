"""Report commands, which are the ones that get printed and posted.

Each of these builds its report out of whatever registers the database holds and
prints it. They take a window because every report a hatchery files is over a
period, and the window is checked before anything is read so a typo in a date
does not come back as an empty report.
"""

from __future__ import annotations

from decimal import Decimal

import click

from ..calendar import DateRange
from ..distribution.release import ReleaseRegister
from ..feed.feeding import Feeding, FeedingLog, FeedMethod
from ..quantities.base import Quantity
from ..rearing.cleaning import CleaningLog
from ..rearing.inventory import take_inventory
from ..rearing.mortality import MortalityCause, MortalityLog, MortalityRecord
from ..rearing.summary import summarise_rearing
from ..reporting.export import write_csv
from ..reporting.lot_history import build_history, render_history
from ..reporting.production import build_production_report, render_production
from ..store.db import query
from ..store.session import Session, open_session
from .main import Context, guard, main, pass_context


def _feeding(session: Session) -> FeedingLog:
    log = FeedingLog()
    for row in query(
        session.connection,
        "SELECT day, lot, feed_lot, amount_kg, method, fed_by FROM feeding ORDER BY day, id",
    ):
        log.record(
            Feeding(
                str(row["day"]),
                str(row["lot"]),
                Quantity(Decimal(str(row["amount_kg"])), "kg"),
                FeedMethod(str(row["method"])),
                str(row["feed_lot"]),
                str(row["fed_by"]),
            )
        )
    return log


def _mortality(session: Session) -> MortalityLog:
    log = MortalityLog()
    for row in query(
        session.connection,
        "SELECT day, lot, count, cause, recorded_by FROM mortality ORDER BY day, id",
    ):
        log.record(
            MortalityRecord(
                str(row["day"]),
                str(row["lot"]),
                Decimal(str(row["count"])),
                MortalityCause(str(row["cause"])),
                str(row["recorded_by"]),
            )
        )
    return log


@main.group()
def report() -> None:
    """Build the reports that get filed."""


@report.command("production")
@click.option("--from", "start", required=True, help="First day of the period.")
@click.option("--to", "end", required=True, help="Last day of the period.")
@pass_context
def production(context: Context, start: str, end: str) -> None:
    """Print the production report for a period."""

    def run() -> None:
        window = DateRange(start, end)
        with open_session(context.database) as session:
            profile = session.profile()
            containers = session.containers()
            lots = list(session.lots())
            inventory = take_inventory(lots, containers, session.ledger(), window.end)
            summary = summarise_rearing(
                inventory, _mortality(session), CleaningLog(), containers, window
            )
            fed = Quantity(0, "kg")
            log = _feeding(session)
            for lot in lots:
                fed = fed + log.fed(str(lot.code), window)
            built = build_production_report(profile, inventory, summary, fed, window.end)
            click.echo(render_production(built, inventory))

    guard(run)


@report.command("lot")
@click.argument("code")
@click.option("--from", "start", default="", help="First day.")
@click.option("--to", "end", default="", help="Last day.")
@click.option("--limit", default=40, show_default=True, help="How many events to show.")
@pass_context
def lot_report(context: Context, code: str, start: str, end: str, limit: int) -> None:
    """Print one lot's whole story."""

    def run() -> None:
        window = DateRange(start, end) if start and end else None
        with open_session(context.database) as session:
            history = build_history(
                code,
                session.ledger(lot=code),
                _mortality(session),
                _feeding(session),
                ReleaseRegister(),
                window=window,
            )
            click.echo(render_history(history, limit=limit))

    guard(run)


@report.command("inventory")
@click.option("--as-of", "as_of", required=True, help="The day to take it on.")
@click.option("--csv", "csv_path", default="", help="Write it to a file instead.")
@pass_context
def inventory(context: Context, as_of: str, csv_path: str) -> None:
    """Print or export the station inventory."""

    def run() -> None:
        with open_session(context.database) as session:
            taken = take_inventory(
                list(session.lots()), session.containers(), session.ledger(), as_of
            )
            headings = ["lot", "unit", "fish", "biomass", "ledger", "loading"]
            rows = [
                [
                    position.lot,
                    position.container,
                    position.population,
                    position.biomass,
                    position.ledger_population,
                    position.status.value,
                ]
                for position in taken.positions
            ]
            if csv_path:
                written = write_csv(csv_path, headings, rows)
                context.say(f"{written} rows written to {csv_path}")
                return
            from .output import Format, echo

            echo(headings, rows, Format.TABLE, places=context.places)
            context.say(taken.line())

    guard(run)
