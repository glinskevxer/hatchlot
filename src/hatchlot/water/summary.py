"""One reading of the whole water system, for the top of a report.

Every piece of this is somewhere else in the package. What is here is the join:
supply against demand, the excursions still open, and the single line a manager
reads first. Keeping the join in its own module means the report layer never has
to know how an excursion is found.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum

from ..calendar import DateRange
from ..quantities.base import Quantity
from ..quantities.temperature import Temperature
from .monitoring import Excursion, MonitoringLog, Thresholds
from .source import SourceRegister


class SupplyState(Enum):
    """How the station is fixed for water, worst last."""

    COMFORTABLE = "comfortable"
    TIGHT = "tight"
    SHORT = "short"


@dataclass(frozen=True, slots=True)
class WaterSummary:
    """The state of the supply and what the meters have been saying."""

    dependable_flow: Quantity
    committed_flow: Quantity
    reuse_fraction: Decimal
    open_excursions: tuple[Excursion, ...]
    mean_temperature: Temperature | None
    units_monitored: int

    @property
    def headroom(self) -> Quantity:
        return self.dependable_flow.to("gpm") - self.committed_flow.to("gpm")

    @property
    def state(self) -> SupplyState:
        """Comfortable above a tenth spare, short once the commitment exceeds supply."""

        dependable = self.dependable_flow.to("gpm").amount
        if dependable == 0:
            return SupplyState.SHORT
        spare = self.headroom.amount / dependable
        if spare < 0:
            return SupplyState.SHORT
        if spare < Decimal("0.1"):
            return SupplyState.TIGHT
        return SupplyState.COMFORTABLE

    @property
    def has_open_excursions(self) -> bool:
        return bool(self.open_excursions)

    def line(self) -> str:
        """The single line that goes at the top of a production report."""

        return (
            f"{self.state.value}: {self.headroom.rounded(0)} spare of "
            f"{self.dependable_flow.rounded(0)}, "
            f"{len(self.open_excursions)} excursions, "
            f"{self.units_monitored} units monitored"
        )


def summarise(
    sources: SourceRegister,
    log: MonitoringLog,
    *,
    committed: Quantity | None = None,
    window: DateRange | None = None,
    thresholds: Thresholds | None = None,
) -> WaterSummary:
    """Pull the water picture together for a window, defaulting to everything."""

    readings = log.within(window) if window is not None else tuple(log)
    scoped = MonitoringLog(readings)
    temperatures = [reading.celsius for reading in readings]
    mean = (
        Temperature(sum(temperatures, Decimal(0)) / Decimal(len(temperatures)), "C")
        if temperatures
        else None
    )
    return WaterSummary(
        dependable_flow=sources.total_dependable_flow(),
        committed_flow=(committed or Quantity(0, "gpm")).to("gpm"),
        reuse_fraction=sources.reuse_fraction(),
        open_excursions=scoped.excursions(thresholds),
        mean_temperature=mean,
        units_monitored=len(scoped.containers()),
    )
