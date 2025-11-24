"""The morning briefing: one command, everything that changed overnight.

This is the command the hatchery manager actually runs. Everything in it is
already somewhere else in the package, and the value is that it is one call
rather than six: what is on hand, what the water did, what has to be fed, and
what wants doing today.

It prints in the order a person reads it. The fish first, because that is what
the job is. The water second, because that is what threatens them. The work
last, because nobody acts on a list they have not had the context for.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal

import click

from ..calendar import DateRange, parse_date
from ..feed.ration import daily_ration, feeding_rate
from ..quantities.base import Quantity
from ..quantities.temperature import Temperature
from ..rearing.inventory import take_inventory
from ..rearing.loading import LoadingStatus
from ..store.db import query
from ..store.session import Session, open_session
from ..water.monitoring import MonitoringLog, Reading, Thresholds
from .main import Context, guarded, main, pass_context
from .options import format_option
from .output import Format, count_line, echo, echo_pairs, parse_format


@dataclass(frozen=True, slots=True)
class Briefing:
    """What the station looks like this morning."""

    lots: int
    fish: Decimal
    biomass: Quantity
    ration: Quantity
    excursions: int
    coldest: Temperature | None
    warmest: Temperature | None
    work: tuple[str, ...]

    @property
    def needs_attention(self) -> bool:
        return bool(self.work)


def _readings(session: Session, window: DateRange) -> MonitoringLog:
    log = MonitoringLog()
    for row in query(
        session.connection,
        "SELECT taken_at, container, celsius, oxygen_mgl FROM water_reading "
        "WHERE substr(taken_at, 1, 10) BETWEEN ? AND ? ORDER BY taken_at",
        window.start.isoformat(),
        window.end.isoformat(),
    ):
        log.record(
            Reading(
                str(row["taken_at"]),
                str(row["container"]),
                Temperature(Decimal(str(row["celsius"])), "C"),
                Decimal(str(row["oxygen_mgl"])),
            )
        )
    return log


def build_briefing(session: Session, as_of: object, water: Temperature) -> Briefing:
    """Gather the morning briefing off whatever the database holds."""

    day = parse_date(as_of)
    window = DateRange(day - timedelta(days=1), day)
    lots = list(session.lots())
    containers = session.containers()
    inventory = take_inventory(lots, containers, session.ledger(), day)
    log = _readings(session, window)
    temperatures = [reading.temperature for reading in log]
    ration = Quantity(0, "kg")
    for lot in lots:
        ration = ration + daily_ration(lot.biomass, feeding_rate(lot.mean_weight, water))
    work: list[str] = []
    for position in inventory.positions:
        if position.status is LoadingStatus.OVER:
            work.append(f"{position.container} is over its loading limit")
        elif position.status is LoadingStatus.WARNING:
            work.append(f"{position.container} is close to its loading limit")
        if not position.agrees_with_ledger:
            work.append(f"{position.lot} is {position.ledger_difference:.0f} off its ledger")
    for homeless in inventory.homeless:
        work.append(f"{homeless} is not in any unit the station has")
    excursions = log.excursions(Thresholds())
    for excursion in excursions:
        work.append(f"{excursion.container} had a {excursion.kind.value} excursion")
    return Briefing(
        lots=len(inventory.positions),
        fish=inventory.population,
        biomass=inventory.biomass,
        ration=ration,
        excursions=len(excursions),
        coldest=min(temperatures) if temperatures else None,
        warmest=max(temperatures) if temperatures else None,
        work=tuple(work),
    )


@main.command()
@click.option("--as-of", "as_of", required=True, help="The morning to brief for.")
@click.option("--water", default="10", show_default=True, help="Water temperature in C.")
@format_option
@guarded
@pass_context
def today(context: Context, as_of: str, water: str, form: str) -> None:
    """Print the morning briefing: what is on hand, what the water did, what to do."""

    with open_session(context.database) as session:
        briefing = build_briefing(session, as_of, Temperature(water, "C"))
    echo_pairs(
        [
            ("lots", Decimal(briefing.lots)),
            ("fish", briefing.fish),
            ("biomass", briefing.biomass.rounded(context.places)),
            ("feed today", briefing.ration.rounded(context.places)),
            ("excursions", Decimal(briefing.excursions)),
            (
                "coldest",
                briefing.coldest.rounded(1) if briefing.coldest is not None else None,
            ),
            (
                "warmest",
                briefing.warmest.rounded(1) if briefing.warmest is not None else None,
            ),
        ],
        parse_format(form),
        places=context.places,
    )
    if briefing.work:
        echo(
            ["to do"],
            [[entry] for entry in briefing.work],
            parse_format(form) if parse_format(form).is_machine else Format.TABLE,
            places=context.places,
        )
    context.say(count_line("job", len(briefing.work)))
