"""The calculators, which are the commands people actually use every day.

None of these touch the database. They are the sums a hatchery does on the back
of a feed bag, done the same way every time and with the refusals in place: a
loading over the limit is a refusal here as much as it is in the engine, because
the whole point is that the answer is the same wherever it is asked for.
"""

from __future__ import annotations

from decimal import Decimal

import click

from ..feed.ration import daily_ration, feeding_rate, feeds_per_day
from ..identifiers import normalise_species
from ..incubation.development import Mark, units_for
from ..quantities.base import Quantity
from ..quantities.temperature import Temperature
from ..species import resolve_species
from ..water.capacity import carrying_capacity
from ..water.oxygen import percent_saturation, saturation_concentration
from .main import Context, guard, main, pass_context
from .output import FORMAT_CHOICE, Format, echo_pairs, parse_format


@main.group()
def calc() -> None:
    """Work out the sums a hatchery does every day."""


@calc.command("loading")
@click.option("--species", required=True, help="Species code or name.")
@click.option("--flow", required=True, help="Flow in gpm.")
@click.option("--volume", required=True, help="Unit volume in cubic feet.")
@click.option("--weight", required=True, help="Mean fish weight in grams.")
@click.option("--water", default="10", show_default=True, help="Water temperature in C.")
@click.option("--inflow", default="10.0", show_default=True, help="Inflow oxygen mg/L.")
@click.option("--floor", default="6.0", show_default=True, help="Oxygen floor mg/L.")
@click.option("--format", "form", type=FORMAT_CHOICE, default=Format.TABLE.value)
@pass_context
def loading(
    context: Context,
    species: str,
    flow: str,
    volume: str,
    weight: str,
    water: str,
    inflow: str,
    floor: str,
    form: str,
) -> None:
    """Say how much fish a unit will carry and which limit binds."""

    def run() -> None:
        stock = resolve_species(species)
        fish_weight = Quantity(weight, "g")
        length = Quantity(
            (fish_weight.to("lb").amount / stock.condition_factor) ** (Decimal(1) / Decimal(3)),
            "in",
        )
        capacity = carrying_capacity(
            flow=Quantity(flow, "gpm"),
            volume=Quantity(volume, "ft3"),
            length=length,
            inflow_mgL=inflow,
            floor_mgL=floor,
            temperature=Temperature(water, "C"),
            fish_weight_g=fish_weight.to("g").amount,
            flow_index=stock.flow_index_limit,
            density_index=stock.density_index_limit,
        )
        echo_pairs(
            [
                ("species", stock.code),
                ("length", length.rounded(context.places)),
                ("oxygen limit", capacity.oxygen.rounded(context.places)),
                ("flow index limit", capacity.flow_index.rounded(context.places)),
                ("density index limit", capacity.density_index.rounded(context.places)),
                ("binding", capacity.binding.value),
                ("allowed", capacity.allowed.rounded(context.places)),
            ],
            parse_format(form),
            places=context.places,
        )

    guard(run)


@calc.command("ration")
@click.option("--biomass", required=True, help="Biomass in kilograms.")
@click.option("--weight", required=True, help="Mean fish weight in grams.")
@click.option("--water", required=True, help="Water temperature in C.")
@click.option("--format", "form", type=FORMAT_CHOICE, default=Format.TABLE.value)
@pass_context
def ration(context: Context, biomass: str, weight: str, water: str, form: str) -> None:
    """Say what a lot is owed for the day, and over how many feedings."""

    def run() -> None:
        fish_weight = Quantity(weight, "g")
        temperature = Temperature(water, "C")
        rate = feeding_rate(fish_weight, temperature)
        amount = daily_ration(Quantity(biomass, "kg"), rate)
        feedings = feeds_per_day(fish_weight)
        echo_pairs(
            [
                ("rate percent", rate),
                ("daily", amount.rounded(context.places)),
                ("feedings", Decimal(feedings)),
                (
                    "per feeding",
                    Quantity(amount.to("kg").amount / Decimal(feedings), "kg").rounded(
                        context.places
                    ),
                ),
            ],
            parse_format(form),
            places=context.places,
        )

    guard(run)


@calc.command("oxygen")
@click.option("--water", required=True, help="Water temperature in C.")
@click.option("--elevation", default="0", show_default=True, help="Metres above sea level.")
@click.option("--measured", default="", help="A meter reading in mg/L.")
@click.option("--format", "form", type=FORMAT_CHOICE, default=Format.TABLE.value)
@pass_context
def oxygen(context: Context, water: str, elevation: str, measured: str, form: str) -> None:
    """Say what the water holds at saturation, and where a reading sits."""

    def run() -> None:
        temperature = Temperature(water, "C")
        ceiling = saturation_concentration(temperature, elevation_m=elevation)
        pairs: list[tuple[str, object]] = [
            ("water", temperature.rounded(1)),
            ("elevation m", Decimal(elevation)),
            ("saturation", ceiling.quantize(Decimal("0.01"))),
        ]
        if measured:
            share = percent_saturation(measured, temperature, elevation_m=elevation)
            pairs.append(("measured", Decimal(measured)))
            pairs.append(("percent of saturation", share.quantize(Decimal("0.1"))))
        echo_pairs(pairs, parse_format(form), places=context.places)

    guard(run)


@calc.command("degree-days")
@click.option("--species", required=True, help="Species code or name.")
@click.option("--water", required=True, help="Mean water temperature in C.")
@click.option("--format", "form", type=FORMAT_CHOICE, default=Format.TABLE.value)
@pass_context
def degree_days(context: Context, species: str, water: str, form: str) -> None:
    """Say how long incubation takes on a steady water."""

    def run() -> None:
        stock = resolve_species(species)
        temperature = Temperature(water, "C")
        above = temperature.celsius - stock.zero_point_c
        if above <= 0:
            raise click.ClickException("that water is at or below the species zero point")
        pairs: list[tuple[str, object]] = [("species", stock.code)]
        for mark in Mark:
            units = units_for(stock, mark)
            days = (units / above).to_integral_value(rounding="ROUND_CEILING")
            pairs.append((f"{mark.value} units", units))
            pairs.append((f"{mark.value} days", days))
        echo_pairs(pairs, parse_format(form), places=context.places)

    guard(run)


@calc.command("species")
@click.argument("name")
@click.option("--format", "form", type=FORMAT_CHOICE, default=Format.TABLE.value)
@pass_context
def species_command(context: Context, name: str, form: str) -> None:
    """Print the constants a species carries."""

    def run() -> None:
        stock = resolve_species(name)
        echo_pairs(
            [
                ("code", normalise_species(stock.code)),
                ("name", stock.common_name),
                ("eye up units", stock.eye_up_units),
                ("hatch units", stock.hatch_units),
                ("swim up units", stock.swim_up_units),
                ("density index", stock.density_index_limit),
                ("flow index", stock.flow_index_limit),
                ("rearing band", f"{stock.rearing_low_c} to {stock.rearing_high_c} C"),
                ("anadromous", stock.anadromous),
            ],
            parse_format(form),
            places=context.places,
        )

    guard(run)
