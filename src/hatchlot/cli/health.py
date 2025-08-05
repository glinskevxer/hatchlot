"""Health commands: the treatment sums, done the same way every time.

These take no database. A treatment is worked out at the raceway with a phone in
one hand, and what matters is that the sum is the one the engine would do and
that the refusals are the ones the engine would raise. A crew that gets a
different number off the command line than off the report has two systems.
"""

from __future__ import annotations

from decimal import Decimal

import click

from ..calendar import parse_date
from ..feed.medicated import Drug, Prescription, inclusion_rate, medicated_feed_needed
from ..health.treatment import (
    Chemical,
    Method,
    Treatment,
    check_oxygen,
    oxygen_headroom_needed,
    safe_ceiling,
)
from ..quantities.base import Quantity
from ..quantities.temperature import Temperature
from .main import Context, guard, main, pass_context
from .options import format_option
from .output import echo, echo_pairs, parse_format


@main.group()
def health() -> None:
    """Work out treatments and the holds they leave behind."""


@health.command("treatment")
@click.option(
    "--chemical",
    type=click.Choice([entry.value for entry in Chemical]),
    required=True,
)
@click.option(
    "--method",
    type=click.Choice([entry.value for entry in Method]),
    default=Method.FLUSH.value,
    show_default=True,
)
@click.option("--concentration", required=True, help="Parts per million.")
@click.option("--minutes", required=True, help="How long it runs.")
@click.option("--water", required=True, help="Water temperature in C.")
@click.option("--flow", default="", help="Flow in gpm, for a flowing treatment.")
@click.option("--volume", default="", help="Volume in cubic metres, for a static bath.")
@click.option("--inflow", default="", help="Inflow oxygen in mg/L, to check the headroom.")
@click.option("--floor", default="6.0", show_default=True, help="Oxygen floor in mg/L.")
@format_option
@pass_context
def treatment(
    context: Context,
    chemical: str,
    method: str,
    concentration: str,
    minutes: str,
    water: str,
    flow: str,
    volume: str,
    inflow: str,
    floor: str,
    form: str,
) -> None:
    """Work out a treatment and check it before it goes in the water."""

    def run() -> None:
        planned = Treatment(
            lot="",
            chemical=Chemical(chemical),
            method=Method(method),
            concentration_ppm=Decimal(concentration),
            minutes=Decimal(minutes),
            water=Temperature(water, "C"),
            volume=Quantity(volume, "m3") if volume else None,
            flow=Quantity(flow, "gpm") if flow else None,
        )
        planned.check()
        if inflow:
            check_oxygen(planned, inflow, floor)
        echo_pairs(
            [
                ("chemical", planned.chemical.value),
                ("method", planned.method.value),
                ("ceiling ppm", safe_ceiling(planned.chemical, planned.water)),
                ("exposure", planned.exposure),
                ("dose", planned.dose.rounded(context.places)),
                ("oxygen cost mgL", oxygen_headroom_needed(planned)),
            ],
            parse_format(form),
            places=context.places,
        )

    guard(run)


@health.command("ceiling")
@click.option("--water", required=True, help="Water temperature in C.")
@format_option
@pass_context
def ceiling(context: Context, water: str, form: str) -> None:
    """List what every chemical may be run at on this water."""

    def run() -> None:
        temperature = Temperature(water, "C")
        echo(
            ["chemical", "ceiling ppm", "takes oxygen"],
            [
                [
                    entry.value,
                    safe_ceiling(entry, temperature),
                    entry.consumes_oxygen,
                ]
                for entry in Chemical
            ],
            parse_format(form),
            places=context.places,
        )

    guard(run)


@health.command("prescription")
@click.option("--lot", "lot_code", required=True, help="The lot to treat.")
@click.option("--drug", type=click.Choice([entry.value for entry in Drug]), required=True)
@click.option("--dose", default="", help="Dose in mg per kg of fish per day.")
@click.option("--days", default=0, help="How long the course runs.")
@click.option("--start", required=True, help="The first day of the course.")
@click.option("--biomass", required=True, help="Biomass in kilograms.")
@click.option("--feeding-rate", "rate", required=True, help="Percent of body weight a day.")
@format_option
@pass_context
def prescription(
    context: Context,
    lot_code: str,
    drug: str,
    dose: str,
    days: int,
    start: str,
    biomass: str,
    rate: str,
    form: str,
) -> None:
    """Turn a prescription into an inclusion rate and a feed order."""

    def run() -> None:
        compound = Drug(drug)
        order = Prescription(
            code="RX",
            lot=lot_code,
            drug=compound,
            dose_mg_per_kg=Decimal(dose) if dose else compound.label_dose_mg_per_kg,
            days=days or compound.label_days,
            start=parse_date(start),
            prescribed_by="vet",
        )
        weight = Quantity(biomass, "kg")
        echo_pairs(
            [
                ("lot", order.lot),
                ("drug", order.drug.value),
                ("dose mg per kg", order.dose_mg_per_kg),
                ("days", Decimal(order.days)),
                ("off label", order.is_off_label),
                ("inclusion mg per kg feed", inclusion_rate(order, rate)),
                (
                    "medicated feed",
                    medicated_feed_needed(order, weight, rate).rounded(context.places),
                ),
                ("withdrawal degree days", order.drug.withdrawal_degree_days),
            ],
            parse_format(form),
            places=context.places,
        )

    guard(run)
