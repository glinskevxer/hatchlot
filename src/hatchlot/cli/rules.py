"""The refusals the package can make, listed so somebody can look one up.

Every `PolicyError` carries a rule name and prints it, which is only useful if
the name can be looked up. This is that list. It is written by hand and checked
against the code by a test, which is the arrangement that survives: an automatic
scan would find the names and none of the explanations.
"""

from __future__ import annotations

from dataclasses import dataclass

import click

from .main import Context, guarded, main, pass_context
from .options import format_option
from .output import count_line, echo, parse_format


@dataclass(frozen=True, slots=True)
class Rule:
    """One refusal, and what a person can do about it."""

    name: str
    area: str
    meaning: str


RULES: tuple[Rule, ...] = (
    Rule("biosecurity.open_case", "health", "the lot has a health case open on it"),
    Rule("biosecurity.restricted", "health", "nothing leaves a quarantine zone"),
    Rule("biosecurity.uphill", "health", "moving to a cleaner zone needs disinfection"),
    Rule("biosecurity.water", "health", "reused water cannot feed a first use zone"),
    Rule("container.out_of_service", "rearing", "the unit is off"),
    Rule("cross.sire_share", "brood", "one male would sire too much of the year class"),
    Rule("feed.empty", "feed", "the feed lot has nothing left in it"),
    Rule("feed.expired", "feed", "the feed is past its date"),
    Rule("feed.short", "feed", "the store has less usable feed than was asked for"),
    Rule("feed.withdrawal", "feed", "a drug withdrawal has not run out yet"),
    Rule("haul.overloaded", "distribution", "the tanks will not carry that load"),
    Rule("haul.tempering", "distribution", "the truck is too far off the receiving water"),
    Rule("incubation.overfill", "incubation", "the tray or jar is full"),
    Rule("incubation.shock_too_early", "incubation", "the lot has not reached eye up"),
    Rule("incubation.stack_limit", "incubation", "the stack has more trays loaded than water"),
    Rule("incubation.tender", "incubation", "the eggs cannot be handled yet"),
    Rule("loading.density_index", "rearing", "the unit is too crowded for the fish in it"),
    Rule("loading.flow_index", "rearing", "the unit has too little water for the fish in it"),
    Rule("loading.oxygen", "rearing", "the water will not breathe for that biomass"),
    Rule("marking.unaccepted", "marking", "no marking run on the group was accepted"),
    Rule("movement.held", "rearing", "the lot is held and does not move"),
    Rule("movement.species", "rearing", "two species cannot be merged"),
    Rule("pedigree.full_sibs", "brood", "those two fish are full siblings"),
    Rule("pedigree.relatedness", "brood", "those two fish are too closely related"),
    Rule("ponding.occupied", "rearing", "the unit already holds a lot"),
    Rule("release.health_hold", "distribution", "the lot is under a health hold"),
    Rule("release.marking", "distribution", "the group has no accepted marking run"),
    Rule("release.request_closed", "distribution", "the request is not open"),
    Rule("release.size", "distribution", "the fish are outside what the request takes"),
    Rule("release.window", "distribution", "the day is outside the request window"),
    Rule("release.withdrawal", "distribution", "a drug withdrawal is outstanding"),
    Rule("sampling.too_small", "rearing", "the sample will not stand for the lot"),
    Rule("shed.no_pairings", "brood", "every ripe hen is too close to every male"),
    Rule("take.culled_female", "brood", "a culled hen cannot be on a spawn take"),
    Rule("take.unknown_female", "brood", "the take names a hen the register never had"),
    Rule("treatment.concentration", "health", "over the safe concentration for this water"),
    Rule("treatment.oxygen", "health", "the treatment would take the unit under its floor"),
)


def rule_named(name: str) -> Rule | None:
    """Look a rule up by the name a refusal printed."""

    for rule in RULES:
        if rule.name == name:
            return rule
    return None


@main.command("rules")
@click.option("--area", default="", help="Only the rules in this area.")
@format_option
@guarded
@pass_context
def rules(context: Context, area: str, form: str) -> None:
    """List the refusals this package can make, and what each one means."""

    found = [rule for rule in RULES if not area or rule.area == area.strip()]
    echo(
        ["rule", "area", "means"],
        [[rule.name, rule.area, rule.meaning] for rule in found],
        parse_format(form),
        places=context.places,
    )
    context.say(count_line("rule", len(found)))
