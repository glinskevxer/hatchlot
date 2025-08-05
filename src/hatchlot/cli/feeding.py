"""Feed commands: what was fed, and what it bought.

The feeding record is the one thing on a hatchery that gets written down twice a
day for a year, so the command that writes it takes as little as it can get away
with: the lot, the day, the amount, the bag. Everything else is worked out.
"""

from __future__ import annotations

from decimal import Decimal

import click

from ..calendar import DateRange, parse_date
from ..feed.conversion import Conversion
from ..feed.feeding import Feeding, FeedingLog, FeedMethod, feed_by_lot
from ..feed.ration import feeding_rate
from ..quantities.base import Quantity
from ..quantities.temperature import Temperature
from ..store.db import execute, query
from ..store.lots import load_lot
from ..store.session import open_session
from .main import Context, guard, main, pass_context
from .options import format_option, window_from, window_options
from .output import count_line, echo, echo_pairs, parse_format


def _log(context: Context, window: DateRange | None = None) -> FeedingLog:
    with open_session(context.database) as session:
        sql = "SELECT day, lot, feed_lot, amount_kg, method, fed_by FROM feeding"
        params: list[object] = []
        if window is not None:
            sql += " WHERE day BETWEEN ? AND ?"
            params = [window.start.isoformat(), window.end.isoformat()]
        sql += " ORDER BY day, id"
        log = FeedingLog()
        for row in query(session.connection, sql, *params):
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


@main.group()
def feed() -> None:
    """Record the feeding and read what it bought."""


@feed.command("record")
@click.option("--lot", "lot_code", required=True, help="The lot that was fed.")
@click.option("--day", required=True, help="The day it was fed.")
@click.option("--amount", required=True, help="How much, in kilograms.")
@click.option("--feed-lot", required=True, help="Which bag it came off.")
@click.option(
    "--method",
    type=click.Choice([entry.value for entry in FeedMethod]),
    default=FeedMethod.HAND.value,
    show_default=True,
)
@click.option("--by", "fed_by", default="hatchery", show_default=True)
@pass_context
def record(
    context: Context,
    lot_code: str,
    day: str,
    amount: str,
    feed_lot: str,
    method: str,
    fed_by: str,
) -> None:
    """Write a feeding down."""

    def run() -> None:
        entry = Feeding(
            day,
            lot_code,
            Quantity(amount, "kg"),
            FeedMethod(method),
            feed_lot,
            fed_by,
        )
        with open_session(context.database) as session:
            load_lot(session.connection, entry.lot)
            execute(
                session.connection,
                "INSERT INTO feeding (day, lot, feed_lot, amount_kg, method, fed_by) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                entry.day.isoformat(),
                entry.lot,
                entry.feed_lot,
                entry.amount.to("kg").amount,
                entry.method.value,
                entry.fed_by,
            )
        context.say(f"{entry.lot} fed {entry.amount.rounded(context.places)}")

    guard(run)


@feed.command("list")
@click.option("--lot", "lot_code", default="", help="Only this lot.")
@window_options()
@format_option
@pass_context
def list_feedings(context: Context, lot_code: str, start: str, end: str, form: str) -> None:
    """List what was fed."""

    def run() -> None:
        window = window_from(start, end)
        log = _log(context, window)
        found = log.for_lot(lot_code) if lot_code else log.all()
        echo(
            ["day", "lot", "feed lot", "amount", "method"],
            [
                [
                    entry.day.isoformat(),
                    entry.lot,
                    entry.feed_lot,
                    entry.amount,
                    entry.method.value,
                ]
                for entry in found
            ],
            parse_format(form),
            places=context.places,
        )
        context.say(count_line("feeding", len(found)))

    guard(run)


@feed.command("totals")
@click.option("--from", "start", required=True, help="First day.")
@click.option("--to", "end", required=True, help="Last day.")
@format_option
@pass_context
def totals(context: Context, start: str, end: str, form: str) -> None:
    """Total the feeding over a window, split by lot."""

    def run() -> None:
        window = DateRange(start, end)
        log = _log(context, window)
        split = feed_by_lot(log, window)
        echo(
            ["lot", "fed", "feed lots"],
            [
                [lot, amount, ", ".join(log.feed_lots_used(lot, window))]
                for lot, amount in sorted(split.items())
            ],
            parse_format(form),
            places=context.places,
        )
        context.say(count_line("lot", len(split)))

    guard(run)


@feed.command("conversion")
@click.option("--lot", "lot_code", required=True, help="The lot to work out.")
@click.option("--from", "start", required=True, help="First day.")
@click.option("--to", "end", required=True, help="Last day.")
@click.option("--opening", required=True, help="Biomass at the start, in kilograms.")
@click.option("--dead", default="0", show_default=True, help="Weight that died.")
@format_option
@pass_context
def conversion(
    context: Context,
    lot_code: str,
    start: str,
    end: str,
    opening: str,
    dead: str,
    form: str,
) -> None:
    """Work out both conversions over a window, against the lot's biomass now."""

    def run() -> None:
        window = DateRange(start, end)
        log = _log(context, window)
        with open_session(context.database) as session:
            record = load_lot(session.connection, lot_code)
        period = Conversion(
            fed=log.fed(lot_code, window),
            opening_biomass=Quantity(opening, "kg"),
            closing_biomass=record.biomass,
            mortality_biomass=Quantity(dead, "kg"),
        )
        echo_pairs(
            [
                ("lot", str(record.code)),
                ("fed", period.fed.rounded(context.places)),
                ("gain", period.gain.rounded(context.places)),
                ("economic", period.economic_ratio.quantize(Decimal("0.001"))),
                ("biological", period.biological_ratio.quantize(Decimal("0.001"))),
                ("plausible", period.is_plausible()),
            ],
            parse_format(form),
            places=context.places,
        )

    guard(run)


@feed.command("rate")
@click.option("--lot", "lot_code", required=True, help="The lot to look up.")
@click.option("--water", required=True, help="Water temperature in C.")
@click.option("--day", default="", help="The day to work it out for.")
@format_option
@pass_context
def rate(context: Context, lot_code: str, water: str, day: str, form: str) -> None:
    """Say what a lot is owed today off its own weight."""

    def run() -> None:
        with open_session(context.database) as session:
            record = load_lot(session.connection, lot_code)
        temperature = Temperature(water, "C")
        share = feeding_rate(record.mean_weight, temperature)
        owed = Quantity(record.biomass.to("kg").amount * share / Decimal(100), "kg")
        echo_pairs(
            [
                ("lot", str(record.code)),
                ("day", (parse_date(day) if day else record.ponded_on).isoformat()),
                ("mean weight", record.mean_weight.rounded(context.places)),
                ("rate percent", share),
                ("owed", owed.rounded(context.places)),
            ],
            parse_format(form),
            places=context.places,
        )

    guard(run)
