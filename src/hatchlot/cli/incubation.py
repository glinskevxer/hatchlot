"""Incubation commands: the room's calendar and the shock arithmetic.

The commands here take a spawn date and a water and answer the two questions the
incubation room asks. When does this lot do the next thing, and is the count that
came off the shock believable. Neither needs the database, because both are
asked about lots that have not been entered yet as often as about lots that have.
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

import click

from ..calendar import parse_date
from ..incubation.development import Mark, is_tender, units_for
from ..incubation.eggslot import EggLot, EggStage
from ..incubation.shock import ShockResult, fertility, is_shock_plausible
from ..incubation.vessel import Vessel, VesselKind
from ..quantities.base import Quantity
from ..species import resolve_species
from .main import Context, guard, main, pass_context
from .options import format_option
from .output import echo, echo_pairs, parse_format


@main.group()
def incubate() -> None:
    """Work out where a lot of eggs is and what is next."""


@incubate.command("schedule")
@click.option("--species", required=True, help="Species code or name.")
@click.option("--spawned", required=True, help="The day the eggs were taken.")
@click.option("--water", required=True, help="Mean water temperature in C.")
@format_option
@pass_context
def schedule(context: Context, species: str, spawned: str, water: str, form: str) -> None:
    """Say when each mark lands on a steady water."""

    def run() -> None:
        stock = resolve_species(species)
        start = parse_date(spawned)
        above = Decimal(water) - stock.zero_point_c
        if above <= 0:
            raise click.ClickException("that water is at or below the species zero point")
        rows = []
        for mark in Mark:
            units = units_for(stock, mark)
            days = int((units / above).to_integral_value(rounding="ROUND_CEILING"))
            rows.append(
                [
                    mark.value,
                    units,
                    Decimal(days),
                    (start + timedelta(days=days - 1)).isoformat(),
                ]
            )
        echo(["mark", "units", "days", "lands on"], rows, parse_format(form), places=context.places)

    guard(run)


@incubate.command("where")
@click.option("--species", required=True, help="Species code or name.")
@click.option("--units", required=True, help="Thermal units taken on so far.")
@format_option
@pass_context
def where(context: Context, species: str, units: str, form: str) -> None:
    """Say what stage a lot is at and whether it can be handled."""

    def run() -> None:
        stock = resolve_species(species)
        taken = Decimal(units)
        passed = [mark for mark in Mark if taken >= units_for(stock, mark)]
        echo_pairs(
            [
                ("species", stock.code),
                ("units", taken),
                ("stage", passed[-1].value if passed else "green"),
                ("tender", is_tender(taken, stock)),
                ("eye up at", stock.eye_up_units),
                ("hatch at", stock.hatch_units),
            ],
            parse_format(form),
            places=context.places,
        )

    guard(run)


@incubate.command("shock")
@click.option("--green", required=True, help="The green egg count.")
@click.option("--standing", default="", help="What was standing at the shock.")
@click.option("--eyed", required=True, help="The eyed count off the shock.")
@format_option
@pass_context
def shock_command(context: Context, green: str, standing: str, eyed: str, form: str) -> None:
    """Read a shock: the eye up rate, the fertility, and whether it is believable."""

    def run() -> None:
        before = Decimal(standing) if standing else Decimal(green)
        result = ShockResult(
            day=parse_date("2000-01-01"),
            before=before,
            eyed=Decimal(eyed),
            whites=before - Decimal(eyed),
        )
        if result.whites < 0:
            raise click.ClickException("more eyed eggs than were standing")
        echo_pairs(
            [
                ("green", Decimal(green)),
                ("standing", before),
                ("eyed", result.eyed),
                ("whites", result.whites),
                ("eye up rate", result.eye_up_rate.quantize(Decimal("0.0001"))),
                ("fertility", fertility(result, green).quantize(Decimal("0.0001"))),
                ("believable", is_shock_plausible(result, green)),
            ],
            parse_format(form),
            places=context.places,
        )

    guard(run)


@incubate.command("capacity")
@click.option("--eggs", required=True, help="How many eggs to hold.")
@click.option("--per-tray", default="12000", show_default=True, help="Tray capacity.")
@click.option("--flow", default="20", show_default=True, help="Flow per tray in Lpm.")
@format_option
@pass_context
def capacity(context: Context, eggs: str, per_tray: str, flow: str, form: str) -> None:
    """Say how many trays a take needs and what water they will want."""

    def run() -> None:
        tray = Vessel(
            code="TR-1",
            kind=VesselKind.TRAY,
            flow=Quantity(flow, "Lpm"),
            capacity_eggs=Decimal(per_tray),
        )
        count = Decimal(eggs)
        if count <= 0:
            raise click.ClickException("that is not a take")
        trays = int((count / tray.capacity()).to_integral_value(rounding="ROUND_CEILING"))
        echo_pairs(
            [
                ("eggs", count),
                ("per tray", tray.capacity()),
                ("trays", Decimal(trays)),
                ("flow", Quantity(tray.flow.to("Lpm").amount * trays, "Lpm")),
            ],
            parse_format(form),
            places=context.places,
        )

    guard(run)


@incubate.command("stages")
@format_option
@pass_context
def stages(context: Context, form: str) -> None:
    """List the stages a lot of eggs goes through, in order."""

    def run() -> None:
        echo(
            ["stage", "order", "closed"],
            [
                [stage.value, Decimal(stage.order), stage.is_closed]
                for stage in sorted(EggStage, key=lambda entry: entry.order)
            ],
            parse_format(form),
            places=context.places,
        )
        context.say(f"a lot starts at {EggLot.__name__.lower()} stage green")

    guard(run)
