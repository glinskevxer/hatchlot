"""Permit commands: what a sample says against a limit, before it is filed.

A discharge sample is a pair of readings and a permit line, and the arithmetic
between them is where the mistakes are: reading the outfall gross when the limit
is net, or comparing a concentration against a mass limit. Both of those are
refusals here rather than a number that looks fine.
"""

from __future__ import annotations

from decimal import Decimal

import click

from ..permits.effluent import estimate_loading, feed_ceiling
from ..permits.limits import (
    Basis,
    Limit,
    Parameter,
    Sample,
    exceeds,
    headroom,
    net_removal,
    share_of_limit,
)
from ..quantities.base import Quantity
from .main import Context, guarded, main, pass_context
from .options import format_option
from .output import echo, echo_pairs, parse_format


def _limit(parameter: str, basis: str, value: str, net: bool) -> Limit:
    return Limit(
        parameter=Parameter(parameter),
        basis=Basis(basis),
        value=Decimal(value),
        net=net,
    )


@main.group()
def permit() -> None:
    """Read a discharge sample against a permit limit."""


@permit.command("sample")
@click.option(
    "--parameter",
    type=click.Choice([entry.value for entry in Parameter]),
    default=Parameter.SUSPENDED_SOLIDS.value,
    show_default=True,
)
@click.option("--intake", required=True, help="The intake reading.")
@click.option("--outfall", required=True, help="The outfall reading.")
@click.option("--limit", "limit_value", required=True, help="The permit number.")
@click.option(
    "--basis",
    type=click.Choice([entry.value for entry in Basis]),
    default=Basis.CONCENTRATION.value,
    show_default=True,
)
@click.option("--gross", is_flag=True, help="The limit is written on the gross reading.")
@click.option("--flow", default="", help="Flow in Lpm, for a mass or feed based limit.")
@click.option("--feed", default="", help="Feed in kilograms, for a feed based limit.")
@format_option
@guarded
@pass_context
def sample_command(
    context: Context,
    parameter: str,
    intake: str,
    outfall: str,
    limit_value: str,
    basis: str,
    gross: bool,
    flow: str,
    feed: str,
    form: str,
) -> None:
    """Read one sample against one limit."""

    limit = _limit(parameter, basis, limit_value, not gross)
    reading = Sample(
        parameter=Parameter(parameter),
        intake=Decimal(intake),
        outfall=Decimal(outfall),
        flow=Quantity(flow, "Lpm") if flow else None,
        feed=Quantity(feed, "kg") if feed else None,
    )
    echo_pairs(
        [
            ("limit", limit.description),
            ("intake", reading.intake),
            ("outfall", reading.outfall),
            ("net", reading.net),
            ("value against the limit", reading.value_for(limit)),
            ("share of the limit", share_of_limit(reading, limit).quantize(Decimal("0.001"))),
            ("headroom", headroom(reading, limit)),
            ("over", exceeds(reading, limit)),
        ],
        parse_format(form),
        places=context.places,
    )


@permit.command("removal")
@click.option("--intake", required=True, help="The intake reading.")
@click.option("--outfall", required=True, help="The outfall reading.")
@format_option
@guarded
@pass_context
def removal(context: Context, intake: str, outfall: str, form: str) -> None:
    """Say what share of what came in the station took out, or added."""

    reading = Sample(
        parameter=Parameter.SUSPENDED_SOLIDS,
        intake=Decimal(intake),
        outfall=Decimal(outfall),
    )
    share = net_removal(reading)
    echo_pairs(
        [
            ("intake", reading.intake),
            ("outfall", reading.outfall),
            ("removal", share.quantize(Decimal("0.0001"))),
            ("adding", share < 0),
        ],
        parse_format(form),
        places=context.places,
    )


@permit.command("feed-ceiling")
@click.option("--limit", "limit_value", required=True, help="The concentration limit.")
@click.option("--flow", required=True, help="Discharge flow in Lpm.")
@click.option("--days", default=30, show_default=True, help="Days in the period.")
@format_option
@guarded
@pass_context
def feed_ceiling_command(
    context: Context, limit_value: str, flow: str, days: int, form: str
) -> None:
    """Say how much feed a concentration limit allows in a period."""

    limit = _limit(Parameter.SUSPENDED_SOLIDS.value, Basis.CONCENTRATION.value, limit_value, True)
    allowed = feed_ceiling(limit, Quantity(flow, "Lpm"), days)
    loading = estimate_loading(allowed)
    echo_pairs(
        [
            ("limit", limit.value),
            ("flow", Quantity(flow, "Lpm")),
            ("days", Decimal(days)),
            ("feed allowed", allowed.rounded(context.places)),
            ("solids", loading.solids.rounded(context.places)),
            ("phosphorus", loading.phosphorus.rounded(context.places)),
        ],
        parse_format(form),
        places=context.places,
    )


@permit.command("loading")
@click.option("--feed", required=True, help="Feed fed over the period, in kilograms.")
@format_option
@guarded
@pass_context
def loading_command(context: Context, feed: str, form: str) -> None:
    """Estimate what a month of feeding puts down the pipe."""

    loading = estimate_loading(Quantity(feed, "kg"))
    echo(
        ["what", "mass"],
        [
            ["solids", loading.solids],
            ["phosphorus", loading.phosphorus],
            ["nitrogen", loading.nitrogen],
        ],
        parse_format(form),
        places=context.places,
    )
    context.say(f"off {loading.feed.rounded(context.places)} of feed")
