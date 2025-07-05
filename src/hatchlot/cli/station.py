"""Station commands: setting a station up and looking at what it has.

These are the commands somebody runs once when the database is new and then
about twice a year. Everything they do could be done with SQL, and the reason
they exist anyway is that the profile has rules on it and a station set up by
hand ends up with a brood year starting in month 13.
"""

from __future__ import annotations

from decimal import Decimal

import click

from ..quantities.base import Quantity
from ..rearing.container import Container, ContainerKind
from ..station import StationProfile
from ..store.repositories import save_container, save_source
from ..store.schema import latest_version
from ..store.session import open_session
from ..units import System
from ..water.source import SourceKind, WaterSource
from .main import Context, guard, main, pass_context
from .output import FORMAT_CHOICE, Format, count_line, echo, echo_pairs, parse_format


@main.group()
def station() -> None:
    """Set the station up and look at what it holds."""


@station.command("init")
@click.option("--code", required=True, help="The station's code.")
@click.option("--name", required=True, help="The station's name.")
@click.option(
    "--system",
    type=click.Choice([entry.value for entry in System]),
    default=System.US.value,
    show_default=True,
    help="Which units the station reports in.",
)
@click.option("--elevation", default="0", show_default=True, help="Metres above sea level.")
@click.option("--brood-month", default=7, show_default=True, help="The month a brood year starts.")
@pass_context
def init(
    context: Context, code: str, name: str, system: str, elevation: str, brood_month: int
) -> None:
    """Create the database and put a station profile in it."""

    def run() -> None:
        profile = StationProfile(
            code=code,
            name=name,
            system=System(system),
            brood_start_month=brood_month,
            elevation_m=Decimal(elevation),
        )
        with open_session(context.database) as session:
            session.save_profile(profile)
            context.say(f"station {profile.code} ready at schema {latest_version()}")

    guard(run)


@station.command("show")
@click.option("--format", "form", type=FORMAT_CHOICE, default=Format.TABLE.value)
@pass_context
def show(context: Context, form: str) -> None:
    """Print the station profile."""

    def run() -> None:
        with open_session(context.database) as session:
            profile = session.profile()
            echo_pairs(
                [
                    ("code", profile.code),
                    ("name", profile.name),
                    ("system", profile.system.value),
                    ("brood month", Decimal(profile.brood_start_month)),
                    ("elevation m", profile.elevation_m),
                    ("schema", Decimal(session.version)),
                ],
                parse_format(form),
                places=context.places,
            )

    guard(run)


@station.command("add-source")
@click.option("--code", required=True, help="The source code.")
@click.option("--name", required=True, help="What the source is called.")
@click.option(
    "--kind",
    type=click.Choice([entry.value for entry in SourceKind]),
    default=SourceKind.SPRING.value,
    show_default=True,
)
@click.option("--flow", required=True, help="Design flow in gpm.")
@click.option("--minimum", default="", help="Dependable minimum flow in gpm.")
@pass_context
def add_source(context: Context, code: str, name: str, kind: str, flow: str, minimum: str) -> None:
    """Put a water source on the station."""

    def run() -> None:
        source = WaterSource(
            code=code,
            name=name,
            kind=SourceKind(kind),
            design_flow=Quantity(flow, "gpm"),
            minimum_flow=Quantity(minimum, "gpm") if minimum else None,
        )
        with open_session(context.database) as session:
            save_source(session.connection, source)
            context.say(f"source {source.code} saved")

    guard(run)


@station.command("add-unit")
@click.option("--code", required=True, help="The unit code.")
@click.option(
    "--kind",
    type=click.Choice([entry.value for entry in ContainerKind]),
    default=ContainerKind.RACEWAY.value,
    show_default=True,
)
@click.option("--length", required=True, help="Length in metres.")
@click.option("--width", required=True, help="Width in metres.")
@click.option("--depth", required=True, help="Water depth in metres.")
@click.option("--flow", required=True, help="Flow in gpm.")
@click.option("--source", default="", help="The water source it runs on.")
@pass_context
def add_unit(
    context: Context,
    code: str,
    kind: str,
    length: str,
    width: str,
    depth: str,
    flow: str,
    source: str,
) -> None:
    """Put a rearing unit on the station."""

    def run() -> None:
        container = Container(
            code=code,
            kind=ContainerKind(kind),
            length=Quantity(length, "m"),
            width=Quantity(width, "m"),
            depth=Quantity(depth, "m"),
            flow=Quantity(flow, "gpm"),
            water_source=source,
        )
        with open_session(context.database) as session:
            save_container(session.connection, container)
            context.say(f"unit {container.code} saved")

    guard(run)


@station.command("units")
@click.option("--format", "form", type=FORMAT_CHOICE, default=Format.TABLE.value)
@click.option("--available", is_flag=True, help="Leave out the units that are off.")
@pass_context
def units(context: Context, form: str, available: bool) -> None:
    """List the rearing units."""

    def run() -> None:
        with open_session(context.database) as session:
            register = session.containers()
            found = register.available() if available else register.all()
            echo(
                ["code", "kind", "volume", "flow", "source", "in service"],
                [
                    [
                        unit.code,
                        unit.kind.value,
                        unit.volume,
                        unit.flow,
                        unit.water_source,
                        unit.is_available(),
                    ]
                    for unit in found
                ],
                parse_format(form),
                places=context.places,
            )
            context.say(count_line("unit", len(found)))

    guard(run)


@station.command("water")
@click.option("--format", "form", type=FORMAT_CHOICE, default=Format.TABLE.value)
@pass_context
def water(context: Context, form: str) -> None:
    """List the water sources and what they are good for."""

    def run() -> None:
        with open_session(context.database) as session:
            register = session.sources()
            echo(
                ["code", "kind", "design", "dependable"],
                [
                    [
                        source.code,
                        source.kind.value,
                        source.design_flow,
                        source.dependable_flow,
                    ]
                    for source in register.all()
                ],
                parse_format(form),
                places=context.places,
            )
            context.say(f"total dependable {register.total_dependable_flow().rounded(0)}")

    guard(run)
