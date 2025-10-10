"""Distribution commands: the truck and what it can carry.

The allocation command is the interesting one. It takes the requests and the
lots as text on the command line, because in the week it matters the requests
are on a spreadsheet somebody emailed and the lots are what the manager knows,
and neither is in the database yet.
"""

from __future__ import annotations

from decimal import Decimal

import click

from ..calendar import DateRange
from ..distribution.allocation import AllocationPolicy, Offer, allocate
from ..distribution.haul import (
    HaulLoad,
    OxygenSupply,
    Tank,
    haul_density,
    loads_needed,
    tempering_minutes,
)
from ..distribution.request import StockingRequest
from ..errors import ValidationError
from ..quantities.base import Quantity
from ..quantities.temperature import Temperature
from .main import Context, guarded, main, pass_context
from .options import format_option
from .output import count_line, echo, echo_pairs, parse_format


def _requests(values: tuple[str, ...], window: DateRange) -> list[StockingRequest]:
    """Read `code:water:species:fish:grams:priority` off the command line."""

    built: list[StockingRequest] = []
    for raw in values:
        parts = raw.split(":")
        if len(parts) < 5:
            raise ValidationError(
                f"{raw!r} is not code:water:species:fish:grams[:priority]", field="request"
            )
        built.append(
            StockingRequest(
                code=parts[0],
                water=parts[1],
                species=parts[2],
                fish=Decimal(parts[3]),
                target_weight=Quantity(parts[4], "g"),
                window=window,
                requested_by="command line",
                priority=int(parts[5]) if len(parts) > 5 else 5,
            )
        )
    return built


def _offers(values: tuple[str, ...], ready: object) -> list[Offer]:
    """Read `lot:species:fish:grams` off the command line."""

    built: list[Offer] = []
    for raw in values:
        parts = raw.split(":")
        if len(parts) != 4:
            raise ValidationError(f"{raw!r} is not lot:species:fish:grams", field="offer")
        built.append(Offer(parts[0], parts[1], Decimal(parts[2]), Quantity(parts[3], "g"), ready))
    return built


@main.group()
def distribute() -> None:
    """Plan the trucks and divide the fish between the waters."""


@distribute.command("allocate")
@click.option(
    "--request", "requests", multiple=True, help="code:water:species:fish:grams[:priority]"
)
@click.option("--offer", "offers", multiple=True, help="lot:species:fish:grams")
@click.option("--from", "start", required=True, help="First day of the window.")
@click.option("--to", "end", required=True, help="Last day of the window.")
@click.option(
    "--policy",
    type=click.Choice([entry.value for entry in AllocationPolicy]),
    default=AllocationPolicy.PRIORITY.value,
    show_default=True,
)
@format_option
@pass_context
@guarded
def allocate_command(
    context: Context,
    requests: tuple[str, ...],
    offers: tuple[str, ...],
    start: str,
    end: str,
    policy: str,
    form: str,
) -> None:
    """Divide the fish that exist among the waters that asked for them."""

    window = DateRange(start, end)
    plan = allocate(
        _requests(requests, window),
        _offers(offers, window.start),
        AllocationPolicy(policy),
    )
    echo(
        ["request", "lot", "fish", "size gap"],
        [[entry.request, entry.lot, entry.fish, entry.size_gap] for entry in plan.assignments],
        parse_format(form),
        places=context.places,
    )
    context.say(plan.line())
    if plan.unfilled:
        context.say(f"unfilled: {', '.join(plan.unfilled)}")


@distribute.command("haul")
@click.option("--fish", required=True, help="How many fish are going.")
@click.option("--weight", required=True, help="Mean weight in grams.")
@click.option("--tank", default="3000", show_default=True, help="Tank volume in litres.")
@click.option("--hours", required=True, help="How long the trip is.")
@click.option("--water", required=True, help="Truck water temperature in C.")
@click.option("--receiving", default="", help="Receiving water temperature in C.")
@format_option
@pass_context
@guarded
def haul_command(
    context: Context,
    fish: str,
    weight: str,
    tank: str,
    hours: str,
    water: str,
    receiving: str,
    form: str,
) -> None:
    """Size a haul, and say how long the tempering will take."""

    truck_water = Temperature(water, "C")
    one_tank = Tank(code="TK-1", volume=Quantity(tank, "L"), supply=OxygenSupply.BOTTLED)
    trips = loads_needed(fish, Quantity(weight, "g"), one_tank, hours, truck_water)
    load = HaulLoad(
        code="HL-1",
        tanks=[one_tank],
        fish=Decimal(fish) / Decimal(trips),
        mean_weight=Quantity(weight, "g"),
        hours=Decimal(hours),
        load_water=truck_water,
        driver="command line",
    )
    pairs: list[tuple[str, object]] = [
        ("fish", Decimal(fish)),
        ("density kg per L", haul_density(hours, truck_water)),
        ("tank capacity", load.capacity.rounded(context.places)),
        ("loads", Decimal(trips)),
        ("fish per load", load.fish.to_integral_value()),
        ("oxygen per load", load.oxygen().rounded(3)),
    ]
    if receiving:
        into = Temperature(receiving, "C")
        pairs.append(("receiving", into.rounded(1)))
        pairs.append(("tempering minutes", Decimal(tempering_minutes(truck_water, into))))
    echo_pairs(pairs, parse_format(form), places=context.places)


@distribute.command("density")
@click.option("--hours", required=True, help="How long the trip is.")
@format_option
@pass_context
@guarded
def density(context: Context, hours: str, form: str) -> None:
    """Show how the haul density falls as the water warms."""

    echo(
        ["water C", "kg per litre"],
        [
            [Decimal(celsius), haul_density(hours, Temperature(celsius, "C"))]
            for celsius in (4, 8, 12, 16, 20)
        ],
        parse_format(form),
        places=4,
    )
    context.say(f"over {hours} hours")


@distribute.command("requests")
@click.option(
    "--request", "requests", multiple=True, help="code:water:species:fish:grams[:priority]"
)
@click.option("--from", "start", required=True, help="First day of the window.")
@click.option("--to", "end", required=True, help="Last day of the window.")
@format_option
@pass_context
@guarded
def requests_command(
    context: Context, requests: tuple[str, ...], start: str, end: str, form: str
) -> None:
    """Read a list of requests back with what each one weighs."""

    window = DateRange(start, end)
    built = _requests(requests, window)
    echo(
        ["code", "water", "species", "fish", "size", "biomass", "priority"],
        [
            [
                entry.code,
                entry.water,
                entry.species,
                entry.fish,
                entry.target_weight,
                entry.biomass(),
                Decimal(entry.priority),
            ]
            for entry in built
        ],
        parse_format(form),
        places=context.places,
    )
    context.say(count_line("request", len(built)))
