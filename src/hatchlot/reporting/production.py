"""The production report, which is the one the agency reads.

It has three parts and they answer three different people. The station summary
is for the manager: what is on hand and how it is doing. The lot table is for
whoever is planning the next month. The exceptions at the bottom are for whoever
has to fix something, and they are last because a report that opens with its
problems gets read as a station in trouble rather than a station that is looking.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from ..calendar import DateRange, parse_date
from ..errors import ValidationError
from ..numeric import safe_divide
from ..quantities.base import Quantity
from ..rearing.inventory import Inventory
from ..rearing.summary import RearingSummary
from ..station import StationProfile
from .tables import Align, Column, bullet_list, heading, join_sections, render_pairs, render_table


@dataclass(frozen=True, slots=True)
class ProductionReport:
    """One period of production, ready to print."""

    station: str
    window: DateRange
    as_of: date
    lots: int
    population: Decimal
    biomass: Quantity
    mortality_rate: Decimal
    fed: Quantity
    exceptions: tuple[str, ...]

    @property
    def is_clean(self) -> bool:
        return not self.exceptions

    @property
    def mean_weight(self) -> Quantity:
        if self.population == 0:
            return Quantity(0, "g")
        return Quantity(
            safe_divide(self.biomass.to("g").amount, self.population, field="population"), "g"
        )

    @property
    def conversion(self) -> Decimal | None:
        """Feed against biomass, which is only a real ratio over a whole period."""

        if self.biomass.to("kg").amount == 0:
            return None
        return safe_divide(self.fed.to("kg").amount, self.biomass.to("kg").amount, field="biomass")


def collect_exceptions(inventory: Inventory, summary: RearingSummary) -> tuple[str, ...]:
    """Everything on the station that somebody has to do something about."""

    found: list[str] = []
    for entry in inventory.overloaded:
        found.append(f"{entry.container} is over its loading limit on {entry.lot}")
    for entry in inventory.disagreeing:
        found.append(f"{entry.lot} is {entry.ledger_difference:.0f} fish off its ledger")
    for lot in inventory.homeless:
        found.append(f"{lot} is not in any unit the station has")
    for container in summary.overdue_cleaning:
        found.append(f"{container} is overdue a cleaning")
    return tuple(found)


def build_production_report(
    profile: StationProfile,
    inventory: Inventory,
    summary: RearingSummary,
    fed: Quantity,
    as_of: object,
) -> ProductionReport:
    """Gather a production report from the registers that hold its parts."""

    return ProductionReport(
        station=profile.name,
        window=summary.window,
        as_of=parse_date(as_of),
        lots=summary.lots,
        population=summary.population,
        biomass=summary.biomass,
        mortality_rate=summary.mortality_rate,
        fed=fed,
        exceptions=collect_exceptions(inventory, summary),
    )


def render_production(report: ProductionReport, inventory: Inventory) -> str:
    """Print the whole report."""

    pairs: list[tuple[str, object]] = [
        ("station", report.station),
        ("period", str(report.window)),
        ("as of", report.as_of.isoformat()),
        ("lots", Decimal(report.lots)),
        ("fish", report.population),
        ("biomass", report.biomass.rounded(1)),
        ("mean weight", report.mean_weight.rounded(2)),
        ("fed", report.fed.rounded(1)),
        ("mortality", report.mortality_rate.quantize(Decimal("0.0001"))),
    ]
    columns = [
        Column(heading="lot"),
        Column(heading="unit"),
        Column(heading="fish", align=Align.RIGHT, places=0),
        Column(heading="biomass", align=Align.RIGHT, places=1),
        Column(heading="loading"),
    ]
    rows = [
        [
            position.lot,
            position.container,
            position.population,
            position.biomass,
            position.status.value,
        ]
        for position in inventory.positions
    ]
    sections = [
        heading(f"Production report {report.window}"),
        render_pairs(pairs),
        render_table(columns, rows),
    ]
    if report.exceptions:
        sections.append(heading("Exceptions", underline="-"))
        sections.append(bullet_list(list(report.exceptions)))
    return join_sections(sections)


def monthly_windows(window: DateRange) -> tuple[DateRange, ...]:
    """Split a period into the calendar months it covers."""

    if window.days > 3660:
        raise ValidationError("that is not a reporting period", field="window")
    months: list[DateRange] = []
    day = window.start
    while day <= window.end:
        month = DateRange.month_of(day)
        months.append(month.clipped_to(window))
        following = month.end
        if following >= window.end:
            break
        day = following.fromordinal(following.toordinal() + 1)
    return tuple(months)
