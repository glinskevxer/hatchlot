"""A self check, for the morning after somebody restored a backup.

Everything in here is a question the station can answer about itself without
knowing what the answer should be: is the schema current, does every lot sit in
a unit that exists, does every lot agree with its own ledger, is anything being
carried that the water will not support. None of it changes anything.

The exit code is the useful part. Clean is zero, findings are two, so this can
go in a cron job and be noticed.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

import click

from ..errors import HatchlotError
from ..rearing.inventory import take_inventory
from ..store.migrations import current_version
from ..store.schema import ALL, latest_version
from ..store.session import Session, open_session
from .main import EXIT_REFUSED, Context, main, pass_context
from .options import format_option
from .output import echo, parse_format


@dataclass(frozen=True, slots=True)
class Check:
    """One question and what the station answered."""

    name: str
    passed: bool
    detail: str

    @property
    def mark(self) -> str:
        return "ok" if self.passed else "check"


def check_schema(session: Session) -> Check:
    version = current_version(session.connection)
    latest = latest_version()
    return Check(
        name="schema",
        passed=version == latest,
        detail=f"at {version} of {latest}",
    )


def check_profile(session: Session) -> Check:
    try:
        profile = session.profile()
    except HatchlotError as error:
        return Check(name="profile", passed=False, detail=str(error))
    return Check(name="profile", passed=True, detail=f"{profile.code} {profile.name}")


def check_units(session: Session) -> Check:
    containers = session.containers()
    off = [unit.code for unit in containers.all() if not unit.is_available()]
    detail = f"{len(containers)} units"
    if off:
        detail += f", off: {', '.join(off)}"
    return Check(name="units", passed=len(containers) > 0, detail=detail)


def check_homes(session: Session) -> Check:
    containers = session.containers()
    homeless = [str(lot.code) for lot in session.lots() if containers.find(lot.container) is None]
    return Check(
        name="homes",
        passed=not homeless,
        detail="every lot is in a unit" if not homeless else ", ".join(homeless),
    )


def check_ledger(session: Session) -> Check:
    off: list[str] = []
    for lot in session.lots():
        code = str(lot.code)
        try:
            balance = session.ledger(lot=code).balance(code)
        except HatchlotError as error:
            off.append(f"{code} ({error})")
            continue
        if balance.closing != lot.population:
            off.append(f"{code} by {lot.population - balance.closing:.0f}")
    return Check(
        name="ledger",
        passed=not off,
        detail="every lot agrees" if not off else ", ".join(off),
    )


def check_loading(session: Session) -> Check:
    lots = list(session.lots())
    containers = session.containers()
    if not lots:
        return Check(name="loading", passed=True, detail="nothing on hand")
    inventory = take_inventory(lots, containers, session.ledger(), "2100-01-01")
    over = [entry.container for entry in inventory.overloaded]
    return Check(
        name="loading",
        passed=not over,
        detail="every unit is inside its limit" if not over else ", ".join(over),
    )


CHECKS = (check_schema, check_profile, check_units, check_homes, check_ledger, check_loading)


def run_checks(session: Session) -> tuple[Check, ...]:
    """Run every check against one open station."""

    return tuple(check(session) for check in CHECKS)


@main.command()
@format_option
@pass_context
def doctor(context: Context, form: str) -> None:
    """Check the database over and exit two if anything wants a look."""

    with open_session(context.database, migrate_to_latest=False) as session:
        if current_version(session.connection) == 0:
            click.echo("this database has no schema in it", err=True)
            raise SystemExit(EXIT_REFUSED)
        results = run_checks(session)
    echo(
        ["check", "result", "detail"],
        [[entry.name, entry.mark, entry.detail] for entry in results],
        parse_format(form),
        places=context.places,
    )
    failed = [entry for entry in results if not entry.passed]
    context.say(f"{len(results) - len(failed)} of {len(results)} checks clear")
    if failed:
        raise SystemExit(EXIT_REFUSED)


@main.command("schema")
@format_option
@pass_context
def schema(context: Context, form: str) -> None:
    """List the migrations and say which have run."""

    with open_session(context.database, migrate_to_latest=False) as session:
        done = current_version(session.connection)
        echo(
            ["version", "name", "applied"],
            [
                [Decimal(migration.version), migration.name, migration.version <= done]
                for migration in ALL
            ],
            parse_format(form),
            places=context.places,
        )
        context.say(f"schema {done} of {latest_version()}")
