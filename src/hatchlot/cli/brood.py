"""Broodstock commands: the spawning shed's arithmetic.

Two of these get used at the shed door. How many hens today, and how many eggs
that should give. The third is the one that stops a bad day: it works a mating
design out and refuses one that leans on a single male, which is a thing nobody
notices until the tag returns come back years later.
"""

from __future__ import annotations

from decimal import Decimal

import click

from ..brood.cross import CrossDesign, plan_cross
from ..brood.eggcount import (
    CountMethod,
    EggEstimate,
    egg_diameter,
    eggs_per_litre,
    reconcile,
    von_bayer_count,
)
from ..brood.fecundity import DEFAULT_MODEL, FecundityModel, females_needed
from ..brood.pedigree import effective_population, inbreeding_rate
from ..quantities.base import Quantity
from .main import Context, guarded, main, pass_context
from .options import format_option
from .output import count_line, echo, echo_pairs, parse_format


@main.group()
def brood() -> None:
    """Work out the spawning."""


@brood.command("target")
@click.option("--eggs", required=True, help="The egg target for the season.")
@click.option("--length", default="78", show_default=True, help="Mean hen length in cm.")
@click.option("--scale", default="", help="A fitted fecundity scale, if there is one.")
@click.option("--exponent", default="", help="A fitted fecundity exponent.")
@format_option
@guarded
@pass_context
def target(context: Context, eggs: str, length: str, scale: str, exponent: str, form: str) -> None:
    """Say how many hens a season's egg target needs."""

    model = (
        FecundityModel(coefficient_scale(scale), Decimal(exponent))
        if scale and exponent
        else DEFAULT_MODEL
    )
    hen = Quantity(length, "cm")
    echo_pairs(
        [
            ("target eggs", Decimal(eggs)),
            ("mean hen", hen),
            ("eggs per hen", model.expected(hen)),
            ("hens needed", Decimal(females_needed(model, eggs, hen))),
        ],
        parse_format(form),
        places=context.places,
    )


def coefficient_scale(value: str) -> Decimal:
    """The fitted scale, refused early so the error names the option."""

    return Decimal(value)


@brood.command("count")
@click.option("--trough", required=True, help="Eggs in twelve inches of trough.")
@click.option("--volume", required=True, help="The volume measured, in litres.")
@click.option("--enumerated", default="", help="A hand count, if there was one.")
@format_option
@guarded
@pass_context
def count(context: Context, trough: str, volume: str, enumerated: str, form: str) -> None:
    """Count a take by the von Bayer method, against a hand count if there is one."""

    diameter = egg_diameter(trough)
    estimate = EggEstimate(von_bayer_count(trough, Quantity(volume, "L")), CountMethod.VON_BAYER)
    estimates = [estimate]
    if enumerated:
        estimates.append(EggEstimate(Decimal(enumerated), CountMethod.ENUMERATED))
    chosen = reconcile(estimates)
    echo_pairs(
        [
            ("egg diameter", diameter.rounded(3)),
            ("eggs per litre", eggs_per_litre(diameter).quantize(Decimal("1"))),
            ("von bayer count", Decimal(estimate.rounded)),
            ("recorded", Decimal(chosen.rounded)),
            ("method", chosen.method.value),
        ],
        parse_format(form),
        places=context.places,
    )


@brood.command("cross")
@click.option("--dam", "dams", multiple=True, required=True, help="A hen. Repeat for more.")
@click.option("--sire", "sires", multiple=True, required=True, help="A buck. Repeat for more.")
@click.option(
    "--design",
    type=click.Choice([entry.value for entry in CrossDesign]),
    default=CrossDesign.FACTORIAL.value,
    show_default=True,
)
@click.option("--max-share", default="0.5", show_default=True, help="Most a buck may sire.")
@format_option
@guarded
@pass_context
def cross(
    context: Context,
    dams: tuple[str, ...],
    sires: tuple[str, ...],
    design: str,
    max_share: str,
    form: str,
) -> None:
    """Work a mating design out into families."""

    plan = plan_cross(CrossDesign(design), list(dams), list(sires), max_sire_share=max_share)
    echo(
        ["family", "dam", "sire"],
        [[family.identifier, family.dam, family.sire] for family in plan.families],
        parse_format(form),
        places=context.places,
    )
    context.say(
        f"{count_line('family', plan.family_count)}, busiest buck {plan.busiest_sire_share():.0%}"
    )


@brood.command("census")
@click.option("--males", required=True, type=int, help="How many bucks were spawned.")
@click.option("--females", required=True, type=int, help="How many hens were spawned.")
@format_option
@guarded
@pass_context
def census(context: Context, males: int, females: int, form: str) -> None:
    """Say what a spawning ratio is really worth in effective population."""

    size = effective_population(males, females)
    echo_pairs(
        [
            ("males", Decimal(males)),
            ("females", Decimal(females)),
            ("parents", Decimal(males + females)),
            ("effective size", size.quantize(Decimal("0.01"))),
            ("inbreeding per generation", inbreeding_rate(size).quantize(Decimal("0.0001"))),
        ],
        parse_format(form),
        places=context.places,
    )
