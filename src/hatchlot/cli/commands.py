"""A listing of what the command line can do, built from the command line.

Written out by hand this would be wrong within a month. Built off the click
group it cannot be, and it doubles as the check that every command has a help
line on it, because a command with no help is a command nobody finds.
"""

from __future__ import annotations

from dataclasses import dataclass

import click

from .main import Context, guarded, main, pass_context
from .options import format_option
from .output import count_line, echo, parse_format


@dataclass(frozen=True, slots=True)
class Entry:
    """One command, and where it sits."""

    group: str
    name: str
    summary: str

    @property
    def path(self) -> str:
        return f"{self.group} {self.name}".strip()


def walk(command: click.Command, prefix: str = "") -> list[Entry]:
    """Walk the command tree into a flat list."""

    found: list[Entry] = []
    if isinstance(command, click.Group):
        for name in sorted(command.commands):
            child = command.commands[name]
            if isinstance(child, click.Group):
                found.extend(walk(child, f"{prefix} {name}".strip()))
            else:
                found.append(
                    Entry(
                        group=prefix,
                        name=name,
                        summary=(child.get_short_help_str() or "").strip(),
                    )
                )
    return found


def missing_help(entries: list[Entry]) -> tuple[str, ...]:
    """Every command that has nothing to say for itself."""

    return tuple(entry.path for entry in entries if not entry.summary)


@main.command("commands")
@click.option("--group", "only", default="", help="Only the commands under this group.")
@format_option
@guarded
@pass_context
def commands(context: Context, only: str, form: str) -> None:
    """List every command, with the one line it says about itself."""

    entries = walk(main)
    if only:
        entries = [entry for entry in entries if entry.group == only.strip()]
    echo(
        ["command", "does"],
        [[entry.path, entry.summary] for entry in entries],
        parse_format(form),
        places=context.places,
    )
    context.say(count_line("command", len(entries)))
