"""Planning commands: what the fish will be, and when.

Every one of these answers a question that gets asked in a meeting: will these
be big enough by April, how much water will they want by then, and what happens
if the winter runs two degrees cold. They all say what they assumed, because a
projection quoted without its water is a projection somebody will hold against
you.
"""

from __future__ import annotations

from decimal import Decimal

import click

from ..calendar import parse_date
from ..growth.model import GrowthModel, fit_coefficient
from ..growth.projection import meets_target, project_to_date, project_to_size
from ..quantities.base import Quantity
from ..quantities.temperature import Temperature
from ..store.lots import load_lot
from ..store.session import open_session
from ..water.thermal import ThermalSeries
from .main import Context, guarded, main, pass_context
from .options import format_option
from .output import echo, echo_pairs, parse_format


@main.group()
def plan() -> None:
    """Work out where the fish will be and when."""


@plan.command("size")
@click.option("--weight", required=True, help="Mean weight now, in grams.")
@click.option("--coefficient", default="2.0", show_default=True, help="Growth coefficient.")
@click.option("--water", required=True, help="Mean water temperature in C.")
@click.option("--from", "start", required=True, help="The day to start from.")
@click.option("--to", "end", required=True, help="The day to project to.")
@click.option("--target", default="", help="A size to check against, in grams.")
@format_option
@pass_context
@guarded
def size(
    context: Context,
    weight: str,
    coefficient: str,
    water: str,
    start: str,
    end: str,
    target: str,
    form: str,
) -> None:
    """Say how big a lot will be on a date."""

    model = GrowthModel(coefficient=Decimal(coefficient))
    projection = project_to_date(
        model,
        Quantity(weight, "g"),
        start,
        end,
        ThermalSeries(),
        assumed_celsius=water,
    )
    pairs: list[tuple[str, object]] = [
        ("from", projection.start_day.isoformat()),
        ("to", projection.end_day.isoformat()),
        ("days", Decimal(projection.days)),
        ("thermal units", projection.thermal_units),
        ("start weight", projection.start_weight.rounded(context.places)),
        ("end weight", projection.end_weight.rounded(context.places)),
        ("assumed water", projection.assumed_celsius),
    ]
    if target:
        pairs.append(("target", Quantity(target, "g")))
        pairs.append(("meets target", meets_target(projection, Quantity(target, "g"))))
    echo_pairs(pairs, parse_format(form), places=context.places)


@plan.command("date")
@click.option("--weight", required=True, help="Mean weight now, in grams.")
@click.option("--target", required=True, help="The size to reach, in grams.")
@click.option("--coefficient", default="2.0", show_default=True, help="Growth coefficient.")
@click.option("--water", required=True, help="Mean water temperature in C.")
@click.option("--from", "start", required=True, help="The day to start from.")
@format_option
@pass_context
@guarded
def date_command(
    context: Context,
    weight: str,
    target: str,
    coefficient: str,
    water: str,
    start: str,
    form: str,
) -> None:
    """Say when a lot reaches a size."""

    model = GrowthModel(coefficient=Decimal(coefficient))
    projection = project_to_size(model, Quantity(weight, "g"), Quantity(target, "g"), start, water)
    echo_pairs(
        [
            ("from", projection.start_day.isoformat()),
            ("reaches", projection.end_day.isoformat()),
            ("days", Decimal(projection.days)),
            ("thermal units", projection.thermal_units),
            ("assumed water", projection.assumed_celsius),
        ],
        parse_format(form),
        places=context.places,
    )


@plan.command("fit")
@click.option("--start-weight", required=True, help="Weight at the first sample, in grams.")
@click.option("--end-weight", required=True, help="Weight at the last sample, in grams.")
@click.option("--units", required=True, help="Thermal units between the two.")
@format_option
@pass_context
@guarded
def fit(context: Context, start_weight: str, end_weight: str, units: str, form: str) -> None:
    """Fit a growth coefficient to what a lot actually did."""

    model = fit_coefficient(Quantity(start_weight, "g"), Quantity(end_weight, "g"), units)
    echo_pairs(
        [
            ("coefficient", model.coefficient.quantize(Decimal("0.0001"))),
            ("start", Quantity(start_weight, "g")),
            ("end", Quantity(end_weight, "g")),
            ("units", Decimal(units)),
        ],
        parse_format(form),
        places=context.places,
    )


@plan.command("lot")
@click.argument("code")
@click.option("--to", "end", required=True, help="The day to project to.")
@click.option("--water", required=True, help="Mean water temperature in C.")
@click.option("--coefficient", default="2.0", show_default=True, help="Growth coefficient.")
@click.option("--as-of", "as_of", default="", help="The day the current weight is from.")
@format_option
@pass_context
@guarded
def lot_plan(
    context: Context,
    code: str,
    end: str,
    water: str,
    coefficient: str,
    as_of: str,
    form: str,
) -> None:
    """Project a lot that is already in the database."""

    with open_session(context.database) as session:
        record = load_lot(session.connection, code)
    model = GrowthModel(coefficient=Decimal(coefficient))
    start = parse_date(as_of) if as_of else record.ponded_on
    projection = project_to_date(
        model,
        record.mean_weight,
        start,
        end,
        ThermalSeries(),
        assumed_celsius=water,
    )
    biomass = Quantity(record.population * projection.end_weight.to("kg").amount, "kg")
    echo(
        ["lot", "fish", "now", "then", "biomass then"],
        [
            [
                str(record.code),
                record.population,
                record.mean_weight,
                projection.end_weight,
                biomass,
            ]
        ],
        parse_format(form),
        places=context.places,
    )
    context.say(f"assuming {Temperature(water, 'C').rounded(1)} over {projection.days} days")
