"""One reading of the incubation room, for the top of a report.

The room has four questions somebody asks every morning: how many eggs are in
it, how they are doing against the losses the station expects, what is coming
up this week, and whether the trays and the records still agree. Each of those
lives in its own module, and this is where they are asked together.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from ..calendar import DateRange, parse_date
from ..errors import ValidationError
from ..numeric import Number, require_non_negative, safe_divide
from ..water.thermal import ThermalSeries
from .eggslot import EggLot, EggStage
from .inventory import Reconciliation, reconcile_room
from .schedule import ScheduleEntry, room_schedule, within
from .vessel import VesselRegister


@dataclass(frozen=True, slots=True)
class RoomSummary:
    """What the incubation room holds and what is about to happen to it."""

    as_of: date
    lots: int
    eggs: Decimal
    by_stage: dict[EggStage, Decimal]
    coming_week: tuple[ScheduleEntry, ...]
    reconciliation: Reconciliation
    survival: Decimal

    @property
    def is_clean(self) -> bool:
        return self.reconciliation.is_clean

    @property
    def eggs_moving(self) -> Decimal:
        return sum((entry.eggs for entry in self.coming_week), Decimal(0))

    def line(self) -> str:
        return (
            f"{self.as_of.isoformat()}: {self.lots} lots, {self.eggs:.0f} eggs, "
            f"{len(self.coming_week)} marks this week, "
            f"{'clean' if self.is_clean else 'needs a count'}"
        )


def summarise_room(
    lots: list[EggLot],
    room: VesselRegister,
    series: ThermalSeries,
    as_of: object,
    *,
    tolerance_percent: Number = 1,
    projection_celsius: Number | None = None,
) -> RoomSummary:
    """Pull the room together as of a day."""

    when = parse_date(as_of)
    live = [lot for lot in lots if not lot.stage.is_closed]
    by_stage: dict[EggStage, Decimal] = {}
    for lot in live:
        by_stage[lot.stage] = by_stage.get(lot.stage, Decimal(0)) + lot.count
    schedule = room_schedule(lots, series, projection_celsius=projection_celsius)
    week = within(schedule, DateRange(when, when + timedelta(days=6)))
    green = sum((lot.green_count for lot in live), Decimal(0))
    standing = sum((lot.count for lot in live), Decimal(0))
    survival = safe_divide(standing, green, field="green_count") if green > 0 else Decimal(0)
    return RoomSummary(
        as_of=when,
        lots=len(live),
        eggs=standing,
        by_stage=by_stage,
        coming_week=week,
        reconciliation=reconcile_room(lots, room, tolerance_percent=tolerance_percent),
        survival=survival,
    )


def expected_standing(lots: list[EggLot], expected_survival: Number = "0.85") -> Decimal:
    """What the room should be holding if losses had run at the usual rate."""

    share = require_non_negative(expected_survival, field="expected_survival")
    if share > 1:
        raise ValidationError("a survival over one is not a survival", field="expected_survival")
    green = sum((lot.green_count for lot in lots if not lot.stage.is_closed), Decimal(0))
    return green * share
