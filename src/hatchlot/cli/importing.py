"""Import commands: getting a datalogger file into the reading table.

The station has one profile built in, for the export the temperature loggers
write, because that is the file every station has. Anything else is a profile
somebody defines, and the command takes the column names on the command line so
that can be done without a release.
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import click

from ..calendar import parse_timestamp
from ..errors import ValidationError
from ..ingest.dedupe import ImportLedger, row_key
from ..ingest.pipeline import rows_of, run_import
from ..ingest.profile import ColumnMap, FieldKind, Profile
from ..quantities.base import Quantity
from ..store.db import execute, query
from ..store.session import Session, open_session
from .main import Context, guard, main, pass_context
from .options import format_option
from .output import count_line, echo, parse_format

LOGGER_PROFILE = Profile(
    code="DATALOGGER",
    description="the export a temperature logger writes",
    columns=[
        ColumnMap(column="DateTime", name="taken_at", kind=FieldKind.TIMESTAMP),
        ColumnMap(
            column="Temp_F",
            name="temperature",
            kind=FieldKind.QUANTITY,
            source_unit="F",
            target_unit="C",
        ),
        ColumnMap(column="Unit", name="container", kind=FieldKind.TEXT),
        ColumnMap(column="DO_mgL", name="oxygen", kind=FieldKind.NUMBER, required=False),
    ],
)


def _ledger(session: Session) -> ImportLedger:
    """Rebuild the dedupe ledger from the readings already stored."""

    ledger = ImportLedger()
    for row in query(session.connection, "SELECT taken_at, container FROM water_reading"):
        ledger.rows.add(
            row_key(
                {
                    "taken_at": parse_timestamp(str(row["taken_at"])),
                    "container": str(row["container"]),
                },
                ("taken_at", "container"),
            )
        )
    return ledger


def _profile(columns: str) -> Profile:
    """Build a profile off a `column=name` list given on the command line."""

    if not columns.strip():
        return LOGGER_PROFILE
    built = Profile(code="ADHOC", description="given on the command line")
    for pair in columns.split(","):
        if "=" not in pair:
            raise ValidationError(f"{pair!r} is not a column mapping", field="columns")
        column, name = (part.strip() for part in pair.split("=", 1))
        kind = {
            "taken_at": FieldKind.TIMESTAMP,
            "container": FieldKind.TEXT,
        }.get(name, FieldKind.NUMBER)
        built.add(ColumnMap(column=column, name=name, kind=kind))
    return built


@main.group("import")
def importing() -> None:
    """Read other people's files in."""


@importing.command("readings")
@click.argument("path", type=click.Path(exists=True, dir_okay=False))
@click.option("--columns", default="", help="A column=name list, if not the logger export.")
@click.option("--dry-run", is_flag=True, help="Read the file and write nothing.")
@pass_context
def readings(context: Context, path: str, columns: str, dry_run: bool) -> None:
    """Import water readings from a file."""

    def run() -> None:
        profile = _profile(columns)
        text = Path(path).read_text(encoding="utf-8")
        with open_session(context.database) as session:
            report = run_import(profile, text, _ledger(session), ("taken_at", "container"))
            if not dry_run:
                for row in rows_of(report):
                    temperature = row.get("temperature")
                    celsius = (
                        temperature.to("C").amount
                        if isinstance(temperature, Quantity)
                        else Decimal(str(temperature))
                    )
                    execute(
                        session.connection,
                        "INSERT INTO water_reading (taken_at, container, celsius, oxygen_mgl) "
                        "VALUES (?, ?, ?, ?) "
                        "ON CONFLICT (taken_at, container) DO UPDATE SET "
                        "celsius = excluded.celsius, oxygen_mgl = excluded.oxygen_mgl",
                        str(row["taken_at"]),
                        str(row.get("container", "")),
                        celsius,
                        Decimal(str(row.get("oxygen", 0))),
                    )
            context.say(report.line())
            if report.rejected:
                context.say(count_line("rejected row", report.rejected))

    guard(run)


@importing.command("check")
@click.argument("path", type=click.Path(exists=True, dir_okay=False))
@click.option("--columns", default="", help="A column=name list, if not the logger export.")
@format_option
@pass_context
def check(context: Context, path: str, columns: str, form: str) -> None:
    """Read a file and report what would happen, without writing anything."""

    def run() -> None:
        profile = _profile(columns)
        text = Path(path).read_text(encoding="utf-8")
        report = run_import(profile, text, ImportLedger(), ("taken_at", "container"))
        echo(
            ["line", "reason"],
            [[Decimal(entry.line), entry.reason] for entry in report.read.rejected],
            parse_format(form),
            places=context.places,
        )
        context.say(f"{report.read.read} rows would read, {len(report.read.rejected)} would not")

    guard(run)


@importing.command("profile")
@format_option
@pass_context
def profile_command(context: Context, form: str) -> None:
    """Print the built in profile, so a vendor file can be matched against it."""

    def run() -> None:
        echo(
            ["column", "name", "kind", "required"],
            [
                [column.column, column.name, column.kind.value, column.required]
                for column in LOGGER_PROFILE.columns
            ],
            parse_format(form),
            places=context.places,
        )

    guard(run)
