"""The options every command was declaring for itself.

Three of them turned up in nearly every command: the output format, a day
window, and who is entering the record. Each was written out in full each time,
and they had already started to drift apart. `--from` was `--start` in one
place, and one listing had lost its `--format` altogether.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, TypeVar

import click

from ..calendar import DateRange
from .output import FORMAT_CHOICE, Format

F = TypeVar("F", bound=Callable[..., Any])


def format_option(command: F) -> F:
    """Add the `--format` option every listing takes."""

    return click.option(
        "--format",
        "form",
        type=FORMAT_CHOICE,
        default=Format.TABLE.value,
        show_default=True,
        help="How to print the answer.",
    )(command)


def window_options(*, required: bool = False) -> Callable[[F], F]:
    """Add the `--from` and `--to` options a report takes."""

    def decorate(command: F) -> F:
        # A required option with a default is not required, because click sees
        # the default and stops asking. So the default only goes on when the
        # window is optional.
        extra: dict[str, Any] = {} if required else {"default": ""}
        command = click.option("--to", "end", required=required, help="Last day.", **extra)(command)
        return click.option("--from", "start", required=required, help="First day.", **extra)(
            command
        )

    return decorate


def entered_by_option(command: F) -> F:
    """Add the `--by` option every command that writes a record takes."""

    return click.option(
        "--by",
        "entered_by",
        default="hatchery",
        show_default=True,
        help="Who is entering this.",
    )(command)


def window_from(start: str, end: str) -> DateRange | None:
    """Turn the two options into a window, or into nothing if neither was given."""

    if start and end:
        return DateRange(start, end)
    if start or end:
        raise click.UsageError("give both --from and --to, or neither")
    return None
