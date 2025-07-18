"""Water commands: the readings and what falls out of them.

The reading commands are the ones a crew runs twice a day, so they are short and
they take the sloppy forms: a unit code however it is written, a temperature in
whichever scale the station reports in, a time or just a day. Everything else in
the group reads those readings back.
"""

from __future__ import annotations

from decimal import Decimal

import click

from ..calendar import DateRange, parse_timestamp
from ..quantities.temperature import Temperature
from ..store.db import execute, query
from ..store.session import open_session
from ..water.monitoring import MonitoringLog, Reading, Thresholds
from .main import Context, guard, main, pass_context
from .output import FORMAT_CHOICE, Format, count_line, echo, echo_pairs, parse_format


def _log_from(rows: list[dict[str, object]]) -> MonitoringLog:
    log = MonitoringLog()
    for row in rows:
        log.record(
            Reading(
                row["taken_at"],
                str(row["container"]),
                Temperature(Decimal(str(row["celsius"])), "C"),
                Decimal(str(row["oxygen_mgl"])),
            )
        )
    return log


def _rows(context: Context, window: DateRange | None = None) -> list[dict[str, object]]:
    with open_session(context.database) as session:
        sql = "SELECT taken_at, container, celsius, oxygen_mgl FROM water_reading"
        params: list[object] = []
        if window is not None:
            sql += " WHERE substr(taken_at, 1, 10) BETWEEN ? AND ?"
            params = [window.start.isoformat(), window.end.isoformat()]
        sql += " ORDER BY taken_at"
        return [dict(row) for row in query(session.connection, sql, *params)]


@main.group()
def water() -> None:
    """Record and read the water."""


@water.command("record")
@click.option("--unit", required=True, help="The unit the reading was taken on.")
@click.option("--at", "taken_at", required=True, help="When it was taken.")
@click.option("--temperature", required=True, help="Water temperature.")
@click.option(
    "--scale",
    type=click.Choice(["C", "F"]),
    default="C",
    show_default=True,
    help="Which scale the temperature is on.",
)
@click.option("--oxygen", required=True, help="Dissolved oxygen in mg/L.")
@pass_context
def record(
    context: Context, unit: str, taken_at: str, temperature: str, scale: str, oxygen: str
) -> None:
    """Put a meter reading on the record."""

    def run() -> None:
        reading = Reading(taken_at, unit, Temperature(temperature, scale), Decimal(oxygen))
        with open_session(context.database) as session:
            execute(
                session.connection,
                "INSERT INTO water_reading (taken_at, container, celsius, oxygen_mgl) "
                "VALUES (?, ?, ?, ?) "
                "ON CONFLICT (taken_at, container) DO UPDATE SET "
                "celsius = excluded.celsius, oxygen_mgl = excluded.oxygen_mgl",
                reading.taken_at.isoformat(),
                reading.container,
                reading.celsius,
                reading.oxygen_mgL,
            )
        context.say(
            f"{reading.container} {reading.temperature.rounded(1)} {reading.oxygen_mgL} mg/L"
        )

    guard(run)


@water.command("list")
@click.option("--unit", default="", help="Only this unit.")
@click.option("--from", "start", default="", help="First day.")
@click.option("--to", "end", default="", help="Last day.")
@click.option("--format", "form", type=FORMAT_CHOICE, default=Format.TABLE.value)
@pass_context
def list_readings(context: Context, unit: str, start: str, end: str, form: str) -> None:
    """List the readings, newest last."""

    def run() -> None:
        window = DateRange(start, end) if start and end else None
        log = _log_from(_rows(context, window))
        found = log.for_container(unit) if unit else tuple(log)
        echo(
            ["taken at", "unit", "temperature", "oxygen"],
            [
                [
                    entry.taken_at.isoformat(sep=" "),
                    entry.container,
                    entry.temperature.rounded(context.places),
                    entry.oxygen_mgL,
                ]
                for entry in found
            ],
            parse_format(form),
            places=context.places,
        )
        context.say(count_line("reading", len(found)))

    guard(run)


@water.command("excursions")
@click.option("--minimum-oxygen", default="6.0", show_default=True)
@click.option("--maximum-temperature", default="16.0", show_default=True)
@click.option("--minimum-temperature", default="2.0", show_default=True)
@click.option("--format", "form", type=FORMAT_CHOICE, default=Format.TABLE.value)
@pass_context
def excursions(
    context: Context,
    minimum_oxygen: str,
    maximum_temperature: str,
    minimum_temperature: str,
    form: str,
) -> None:
    """Collapse the bad readings into excursions."""

    def run() -> None:
        thresholds = Thresholds(
            minimum_oxygen_mgL=Decimal(minimum_oxygen),
            maximum_celsius=Decimal(maximum_temperature),
            minimum_celsius=Decimal(minimum_temperature),
        )
        log = _log_from(_rows(context))
        found = log.excursions(thresholds)
        echo(
            ["unit", "kind", "from", "to", "worst", "readings"],
            [
                [
                    entry.container,
                    entry.kind.value,
                    entry.started_at.isoformat(sep=" "),
                    entry.ended_at.isoformat(sep=" "),
                    entry.worst,
                    Decimal(entry.readings),
                ]
                for entry in found
            ],
            parse_format(form),
            places=context.places,
        )
        context.say(count_line("excursion", len(found)))

    guard(run)


@water.command("latest")
@click.argument("unit")
@click.option("--format", "form", type=FORMAT_CHOICE, default=Format.TABLE.value)
@pass_context
def latest(context: Context, unit: str, form: str) -> None:
    """Print the last reading on a unit and the mean behind it."""

    def run() -> None:
        log = _log_from(_rows(context))
        found = log.latest(unit)
        if found is None:
            raise click.ClickException(f"no readings on {unit}")
        echo_pairs(
            [
                ("unit", found.container),
                ("taken at", parse_timestamp(found.taken_at).isoformat(sep=" ")),
                ("temperature", found.temperature.rounded(context.places)),
                ("oxygen", found.oxygen_mgL),
                ("mean oxygen", log.mean_oxygen(found.container).quantize(Decimal("0.01"))),
            ],
            parse_format(form),
            places=context.places,
        )

    guard(run)
