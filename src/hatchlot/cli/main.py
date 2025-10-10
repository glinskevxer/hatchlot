"""The command line entry point, and what happens when something goes wrong.

Three exit codes and they mean different things. Zero is fine. Two is the
station saying no: a validation error, a rule refusing, a record that is not
there. Anything else is a bug in this package, and it comes with a traceback
because hiding it helps nobody.

A `PolicyError` is worth calling out separately in the output even though it
exits the same way, because a rule refusing an operation is a thing the operator
may be able to argue with and a validation error is not.
"""

from __future__ import annotations

import functools
import sys
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, TypeVar, cast

import click

from .. import __version__
from ..errors import HatchlotError, NotFoundError, PolicyError, ValidationError

EXIT_OK = 0
EXIT_REFUSED = 2

F = TypeVar("F", bound=Callable[..., Any])


@dataclass
class Context:
    """What every command needs: where the database is and how loud to be."""

    database: str = ":memory:"
    quiet: bool = False
    places: int = 2

    def say(self, message: str) -> None:
        if not self.quiet:
            click.echo(message)


pass_context = click.make_pass_decorator(Context, ensure=True)


def describe_error(error: HatchlotError) -> str:
    """The one line a refusal prints."""

    if isinstance(error, PolicyError):
        return f"refused by {error.rule}: {error}"
    if isinstance(error, NotFoundError):
        return f"not found: {error}"
    if isinstance(error, ValidationError):
        return f"invalid: {error}"
    return f"error: {error}"


def run_guarded(action: Callable[[], Any]) -> int:
    """Run a command body, turning a deliberate error into an exit code."""

    try:
        action()
    except HatchlotError as error:
        click.echo(describe_error(error), err=True)
        return EXIT_REFUSED
    return EXIT_OK


def guard(action: Callable[[], Any]) -> None:
    """Run a command body and exit with the right code."""

    code = run_guarded(action)
    if code != EXIT_OK:
        raise SystemExit(code)


def guarded(command: F) -> F:
    """Wrap a command body so a deliberate error becomes an exit code.

    Every command was doing this by hand, with an inner function and a call to
    `guard`, which is four lines of ceremony per command and one more place for
    a command to forget.
    """

    @functools.wraps(command)
    def wrapper(*args: Any, **kwargs: Any) -> None:
        try:
            command(*args, **kwargs)
        except HatchlotError as error:
            click.echo(describe_error(error), err=True)
            raise SystemExit(EXIT_REFUSED) from None

    return cast("F", wrapper)


@click.group(context_settings={"help_option_names": ["-h", "--help"]})
@click.version_option(version=__version__, prog_name="hatchlot")
@click.option(
    "--database",
    "-d",
    default=":memory:",
    show_default=True,
    help="The station database to work on.",
)
@click.option("--quiet", "-q", is_flag=True, help="Print only what was asked for.")
@click.option(
    "--places",
    default=2,
    show_default=True,
    help="Decimal places on printed numbers.",
)
@click.pass_context
def main(ctx: click.Context, database: str, quiet: bool, places: int) -> None:
    """Production records for a coldwater salmonid hatchery."""

    if places < 0 or places > 6:
        raise click.BadParameter("places runs from 0 to 6", param_hint="--places")
    ctx.obj = Context(database=database, quiet=quiet, places=places)


@main.command()
@pass_context
def version(context: Context) -> None:
    """Print the version and the database being used."""

    context.say(f"hatchlot {__version__}")
    context.say(f"database {context.database}")


def entry() -> None:  # pragma: no cover - the console script
    """The console script, which turns an unexpected error into a traceback."""

    try:
        main.main(standalone_mode=False)
    except click.ClickException as error:
        error.show()
        sys.exit(error.exit_code)
    except HatchlotError as error:
        click.echo(describe_error(error), err=True)
        sys.exit(EXIT_REFUSED)
